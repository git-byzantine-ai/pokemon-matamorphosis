-- The build script substitutes the ELF-derived bridge address below.
-- mGBA 0.10+; all image generation runs outside the frame callback.
local BASE = @BRIDGE_ADDRESS@
local ASSETS = @ASSET_ADDRESS@
local MAGIC = 0x4D41544D
local EVENTS = BASE + 132
local CACHE = EVENTS + 128 * 36
local SLOTS = 2
local INCOMING_BANK = CACHE + SLOTS * 8
local MENU = INCOMING_BANK + 4
local conn, pending, receiveBuffer = nil, nil, ''
local frames, nextSlot, lastSequence, lastCampaign, lastHead = 0, 0, nil, nil, nil
local function r32(addr) return emu:read32(addr) end
local function w32(addr, value) emu:write32(addr, value) end
local function rom32(addr, value) emu.memory.cart0:write32(addr - emu.memory.cart0:base(), value) end
local function slotAddress(index)
    local metadata = CACHE + index * 8
    local bank = r32(metadata)
    if bank < 1 or bank > 3 then return nil end
    local addr = ASSETS + (bank-1) * 4148
    if r32(addr) ~= MAGIC or r32(addr+16) ~= r32(metadata+4) then return nil end
    return addr
end
local function hex32(value) return string.format('%08x', value) end
local function hashKey(cp) return hex32(r32(cp + 16)) .. hex32(r32(cp + 12)) end
local function campaign(cp) return hex32(r32(cp + 8)) .. hex32(r32(cp + 4)) end
local function toHex(raw) return (raw:gsub('.', function(c) return string.format('%02x', string.byte(c)) end)) end
local function fromHex(raw)
    if #raw % 2 ~= 0 or raw:find('[^0-9a-f]') then error('invalid sprite hex') end
    return (raw:gsub('..', function(h) return string.char(tonumber(h, 16)) end))
end
local function disconnect(message)
    if conn then pcall(function() conn:close() end) end
    conn, pending, receiveBuffer = nil, nil, ''
    console:error('Metamorphosis: ' .. tostring(message))
end
local function send(line, request)
    local sent, err = conn:send(line .. '\n')
    if not sent or sent < #line + 1 then disconnect(err or 'partial command write'); return end
    pending = request
    pending.started = frames
end
local function invalidate()
    for i = 0, SLOTS-1 do w32(CACHE + i * 8, 0) end
    w32(BASE + 32, 0)
    pending = nil
end
local function process(line, cp)
    local request = pending
    pending = nil
    if not request then return end
    local parts = {}
    for word in line:gmatch('%S+') do table.insert(parts, word) end
    if parts[1] == 'ERROR' then
        if request.kind == 'menu' and r32(MENU) == request.id then w32(MENU+4,3) end
        disconnect(line); return
    end
    if request.kind == 'hello' then
        if line ~= 'OK 6' then disconnect('protocol mismatch') end
    elseif request.kind == 'menu' then
        if r32(MENU) ~= request.id or r32(MENU+4) ~= 1
          or campaign(cp) ~= request.campaign or hashKey(cp) ~= request.head then return end
        if #parts ~= 5 or parts[1] ~= 'ESSENCE' or parts[2] ~= request.head
          or tonumber(parts[3]) ~= request.offset then w32(MENU+4,3); return end
        local total=tonumber(parts[4])
        if not total or total<0 or total>411 then w32(MENU+4,3); return end
        local count=0
        if parts[5] ~= '-' then
            for entry in parts[5]:gmatch('[^;]+') do
                local species,available,used=entry:match('^(%d+),(%d+),(%d+)$')
                species,available,used=tonumber(species),tonumber(available),tonumber(used)
                if not species or not available or not used or used<0 or used>255 or used>available or species<1 or species>411
                  or available<1 or available>65535 or count>=8 then w32(MENU+4,3); return end
                emu:write16(MENU+28+count*6,species)
                emu:write16(MENU+30+count*6,available)
                emu:write16(MENU+32+count*6,used)
                count=count+1
            end
        end
        emu:write16(MENU+22,total)
        emu:write16(MENU+24,count)
        w32(MENU+4,2) -- Publish the complete page last.
    elseif request.kind == 'progress' then
        if r32(MENU) ~= request.id or emu:read8(MENU+19)==0
          or campaign(cp) ~= request.campaign or hashKey(cp) ~= request.head then return end
        if #parts~=4 or parts[1]~='PROGRESS' or parts[2]~=request.head then return end
        local phase=tonumber(parts[4])
        local asset=tonumber(parts[3],16)
        if not phase or phase<0 or phase>4 or not asset then return end
        w32(MENU+80,asset)
        w32(MENU+76,phase)
    elseif request.kind == 'event' then
        if parts[1] ~= 'ACK' or parts[2] ~= request.head then disconnect('incorrect history acknowledgement'); return end
        -- Do not advance a restored/replaced queue with an acknowledgement from its future.
        if campaign(cp) == request.campaign and r32(BASE + 20) == request.read
          and toHex(emu:readRange(EVENTS + (request.read % 128) * 36, 36)) == request.event then
            w32(BASE + 20, request.read + 1)
        end
    elseif request.kind == 'poll' and parts[1] == 'ASSET' then
        if campaign(cp) ~= request.campaign or hashKey(cp) ~= parts[2] or request.head ~= parts[2] then return end
        if #parts ~= 9 or r32(BASE + 32) ~= 0 then return end
        local payload = fromHex(parts[9])
        if #payload ~= 4128 then disconnect('incorrect sprite length'); return end
        local pid, ot = tonumber(parts[3],16), tonumber(parts[4],16)
        local chosen = nextSlot
        local used = {}
        for i = 0, SLOTS-1 do
            used[r32(CACHE+i*8)] = true
        end
        for i = 0, SLOTS-1 do
            local slot = slotAddress(i)
            if slot and r32(slot + 4) == pid and r32(slot + 8) == ot then chosen = i; break end
            if not slot then chosen = i end
        end
        nextSlot = (chosen + 1) % SLOTS
        local bank = 1
        while used[bank] do bank = bank + 1 end
        if bank > 3 then disconnect('no inactive ROM sprite bank'); return end
        local incoming = ASSETS + (bank-1) * 4148
        rom32(incoming, 0)
        rom32(incoming + 4, pid)
        rom32(incoming + 8, ot)
        rom32(incoming + 12, tonumber(parts[5]) + tonumber(parts[6])*65536)
        rom32(incoming + 16, tonumber(parts[7],16))
        for offset = 0, #payload - 1, 4 do
            local a,b,c,d = payload:byte(offset+1, offset+4)
            rom32(incoming + 20 + offset, a + b*256 + c*65536 + d*16777216)
        end
        rom32(incoming, MAGIC)
        w32(INCOMING_BANK, bank-1)
        w32(BASE + 36, chosen)
        w32(BASE + 40, tonumber(parts[8],16))
        w32(BASE + 32, 1) -- Commit flag is always last.
    end
end
local function tick()
    frames = frames + 1
    if r32(BASE) ~= MAGIC then return end
    if r32(BASE + 4) ~= 6 or r32(BASE + 8) ~= 0xC75F3521 then error('wrong ROM protocol/build') end
    local cp = r32(BASE + 12)
    if cp < 0x02000000 or cp >= 0x02040000 or r32(cp) ~= MAGIC then return end
    if r32(cp + 4) == 0 and r32(cp + 8) == 0 then
        -- Campaign randomness belongs to Lua, never the game's battle RNG.
        w32(cp + 4, math.random(1, 0x7ffffffe))
        w32(cp + 8, math.random(1, 0x7ffffffe))
    end
    local currentCampaign, currentHead, sequence = campaign(cp), hashKey(cp), r32(cp + 20)
    if lastCampaign and (lastCampaign ~= currentCampaign or sequence < lastSequence
      or (sequence == lastSequence and currentHead ~= lastHead)) then
        invalidate()
        if conn then disconnect('save-state timeline changed; reconnecting') end
    end
    lastCampaign, lastHead, lastSequence = currentCampaign, currentHead, sequence
    if not conn then
        if frames % 120 ~= 0 then return end
        conn = socket.tcp()
        local connected, err = conn:connect('127.0.0.1', 8765)
        if not connected then disconnect('Start the metamorphosis companion: ' .. tostring(err)); return end
        send('HELLO 6 c75f3521', {kind='hello'})
        return
    end
    w32(BASE + 28, 180)
    do
        local chunk, err = conn:receive(32768)
        if chunk and #chunk == 0 then disconnect('connection closed'); return end
        if not chunk and err ~= socket.ERRORS.AGAIN then disconnect(err); return end
        if chunk then receiveBuffer = receiveBuffer .. chunk end
        if #receiveBuffer > 65536 then disconnect('oversized response'); return end
        local newline = receiveBuffer:find('\n', 1, true)
        if newline then
            local line = receiveBuffer:sub(1, newline-1)
            receiveBuffer = receiveBuffer:sub(newline+1)
            process(line, cp)
        end
    end
    if pending and frames - pending.started > 600 then disconnect('companion response timed out'); return end
    if not conn or pending then return end
    local write, read = r32(BASE + 16), r32(BASE + 20)
    if write ~= read then
        local addr = EVENTS + (read % 128) * 36
        local event = toHex(emu:readRange(addr,36))
        local eventHead = hex32(r32(addr+16)) .. hex32(r32(addr+12))
        send('EVENT ' .. currentCampaign .. ' ' .. event, {kind='event', campaign=currentCampaign, read=read, event=event, head=eventHead})
    elseif r32(MENU+4) == 1 then
        local offset=emu:read16(MENU+20)
        local descriptor=hex32(r32(MENU+12))..','..hex32(r32(MENU+8))..','..emu:read16(MENU+16)..','..emu:read8(MENU+18)
        send('MENU '..currentCampaign..' '..currentHead..' '..descriptor..' '..offset,
             {kind='menu',id=r32(MENU),offset=offset,campaign=currentCampaign,head=currentHead})
    elseif emu:read8(MENU+19) ~= 0 and frames % 30 == 1 then
        local descriptor=hex32(r32(MENU+12))..','..hex32(r32(MENU+8))..','..emu:read16(MENU+16)..','..emu:read8(MENU+18)
        send('PROGRESS '..currentCampaign..' '..currentHead..' '..descriptor,
             {kind='progress',id=r32(MENU),campaign=currentCampaign,head=currentHead})
    elseif frames % 15 == 0 and r32(BASE+32) == 0 then
        local known, wanted, seen = {}, {}, {}
        for i=0,SLOTS-1 do
            local addr=slotAddress(i)
            if addr then table.insert(known,hex32(r32(addr+16))) end
        end
        -- Displayed boxed individual takes priority over inactive party members.
        local order={6,0,1,2,3,4,5}
        for _,i in ipairs(order) do
            local addr=BASE+48+i*12
            if emu:read8(addr+11) ~= 0 then
                local pid,ot=hex32(r32(addr)),hex32(r32(addr+4))
                local key=ot..':'..pid
                if not seen[key] and #wanted < SLOTS then
                    seen[key]=true
                    table.insert(wanted,ot..','..pid..','..emu:read16(addr+8)..','..emu:read8(addr+10))
                end
            end
        end
        send('POLL '..currentCampaign..' '..currentHead..' '..(#known>0 and table.concat(known,',') or '-')..' '..(#wanted>0 and table.concat(wanted,';') or '-'), {kind='poll',campaign=currentCampaign,head=currentHead})
    end
end
math.randomseed(os.time())
callbacks:add('frame',function()
    local ok,err=pcall(tick)
    if not ok then disconnect(err) end
end)
console:log('Metamorphosis bridge loaded. Start the companion before earning experience.')
