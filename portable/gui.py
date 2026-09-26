"""Small first-run wizard and launcher; no shell or administrator access needed."""
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import webbrowser
from pathlib import Path
from . import VERSION
from .backend import Installation,Session
from .windows import DataLock


class Launcher:
    def __init__(self,data):
        self.root=tk.Tk();self.root.title('Pokémon Metamorphosis');self.root.geometry('820x760');self.root.minsize(760,710)
        self.events=queue.Queue();self.busy=False;self.cancel=threading.Event();self.session=None;self.lock=None
        self.install=Installation(data);self.lock=DataLock(self.install.data/'launcher.lock')
        style=ttk.Style();style.theme_use('clam')
        style.configure('.',font=('Segoe UI',10));style.configure('TFrame',background='#edf2f4')
        style.configure('TLabel',background='#edf2f4',foreground='#223944')
        style.configure('Title.TLabel',font=('Segoe UI',23,'bold'))
        style.configure('Heading.TLabel',font=('Segoe UI',12,'bold'))
        style.configure('TButton',padding=(12,6));style.configure('Accent.TButton',background='#176859',foreground='white')
        frame=ttk.Frame(self.root,padding=18);frame.pack(fill='both',expand=True);frame.columnconfigure(0,weight=1)
        ttk.Label(frame,text='Pokémon Metamorphosis',style='Title.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(frame,text=f'Windows portable • {VERSION} • local AI, no API key').grid(row=1,column=0,sticky='w',pady=(4,12))
        ttk.Label(frame,text='1  Prepare your game',style='Heading.TLabel').grid(row=2,column=0,sticky='w')
        ttk.Label(frame,text='Choose an original English FireRed v1.0 ROM. Setup makes a patched copy.').grid(row=3,column=0,sticky='w',pady=(4,6))
        self.rom=tk.StringVar();self.model=tk.StringVar();self.status=tk.StringVar(value='Select your ROM, then run setup.');self.link=tk.StringVar(value='Game is not running.')
        self.buttons=[]
        self.path_row(frame,4,self.rom,'Choose ROM',self.choose_rom)
        self.path_row(frame,5,self.model,'Existing model…',self.choose_model)
        ttk.Label(frame,text='Optional: reuse DreamShaper 8. Otherwise setup downloads it (about 2 GB).').grid(row=6,column=0,sticky='w',pady=(1,8))
        bar=ttk.Frame(frame);bar.grid(row=7,column=0,sticky='w')
        self.setup_button=ttk.Button(bar,text='Set up / Repair',command=self.setup,style='Accent.TButton');self.setup_button.pack(side='left');self.buttons.append(self.setup_button)
        self.pause=ttk.Button(bar,text='Pause download',command=self.cancel.set,state='disabled');self.pause.pack(side='left',padx=8)
        self.progress=ttk.Progressbar(frame,maximum=100);self.progress.grid(row=8,column=0,sticky='ew',pady=(12,4))
        ttk.Label(frame,textvariable=self.status,wraplength=750).grid(row=9,column=0,sticky='w',pady=(0,16))
        ttk.Separator(frame).grid(row=10,column=0,sticky='ew',pady=6)
        ttk.Label(frame,text='2  Check image generation',style='Heading.TLabel').grid(row=11,column=0,sticky='w',pady=(8,6))
        devices=ttk.Frame(frame);devices.grid(row=12,column=0,sticky='ew');devices.columnconfigure(0,weight=1)
        self.device=ttk.Combobox(devices,state='readonly');self.device.grid(row=0,column=0,sticky='ew')
        self.device.bind('<<ComboboxSelected>>',self.device_changed)
        self.test=ttk.Button(devices,text='Test AI',command=self.test_ai);self.test.grid(row=0,column=1,padx=(8,0));self.buttons.append(self.test)
        ttk.Label(frame,text='The test creates a front/back sprite pair. GPU: usually a few minutes. CPU: much slower.',wraplength=740).grid(row=13,column=0,sticky='w',pady=(5,14))
        ttk.Label(frame,text='3  Play',style='Heading.TLabel').grid(row=14,column=0,sticky='w')
        actions=ttk.Frame(frame);actions.grid(row=15,column=0,sticky='w',pady=8)
        self.play=ttk.Button(actions,text='Play',command=self.start,style='Accent.TButton');self.play.pack(side='left');self.buttons.append(self.play)
        self.copy=ttk.Button(actions,text='Copy bridge path',command=self.copy_bridge);self.copy.pack(side='left',padx=8)
        self.dashboard=ttk.Button(actions,text='Sprite dashboard',command=self.open_dashboard);self.dashboard.pack(side='left')
        ttk.Label(frame,text='Each time mGBA opens: Tools → Scripting → File → Load script, then paste the bridge path.\nKeep this launcher open while playing. Use normal in-game saves when updating.',wraplength=750).grid(row=16,column=0,sticky='w',pady=(0,7))
        ttk.Label(frame,textvariable=self.link,wraplength=750).grid(row=17,column=0,sticky='w')
        ttk.Separator(frame).grid(row=18,column=0,sticky='ew',pady=9)
        bottom=ttk.Frame(frame);bottom.grid(row=19,column=0,sticky='ew')
        ttk.Button(bottom,text='Open data folder',command=lambda:os.startfile(self.install.data)).pack(side='left')
        self.change=ttk.Button(bottom,text='Change data folder',command=self.change_data);self.change.pack(side='left',padx=8);self.buttons.append(self.change)
        self.backup=ttk.Button(bottom,text='Back up save',command=self.make_backup);self.backup.pack(side='left');self.buttons.append(self.backup)
        ttk.Button(bottom,text='Help',command=self.help).pack(side='left',padx=8)
        self.location=ttk.Label(frame,text=str(self.install.data),wraplength=750);self.location.grid(row=20,column=0,sticky='w',pady=(6,0))
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh();self.root.after(150,self.poll)

    def path_row(self,parent,row,value,label,action):
        f=ttk.Frame(parent);f.grid(row=row,column=0,sticky='ew',pady=3);f.columnconfigure(0,weight=1)
        ttk.Entry(f,textvariable=value).grid(row=0,column=0,sticky='ew')
        b=ttk.Button(f,text=label,command=action);b.grid(row=0,column=1,padx=(8,0));self.buttons.append(b)

    def choose_rom(self):
        value=filedialog.askopenfilename(title='Select original FireRed v1.0 ROM',filetypes=[('GBA ROM','*.gba')])
        if value:self.rom.set(value)

    def choose_model(self):
        value=filedialog.askopenfilename(title='Optional existing DreamShaper 8 model',filetypes=[('Model','*.safetensors')])
        if value:self.model.set(value)

    def refresh(self):
        state=self.install.state();found=state.get('devices',[])
        self.device['values']=[f"{d['id']} — {d['name']}" for d in found]
        for i,d in enumerate(found):
            if d['id']==state.get('device'):self.device.current(i)
        ready=self.install.ready();running=self.session and self.session.game and self.session.game.poll() is None
        for b in self.buttons:b.configure(state='disabled' if self.busy or running else 'normal')
        self.test.configure(state='normal' if ready and not self.busy and not running else 'disabled')
        self.play.configure(state='normal' if ready and state.get('ai_check') and not self.busy and not running else 'disabled')
        self.device.configure(state='readonly' if ready and not self.busy and not running else 'disabled')
        self.pause.configure(state='normal' if self.busy and self.task=='setup' else 'disabled')
        self.copy.configure(state='normal' if self.session else 'disabled');self.dashboard.configure(state='normal' if self.session else 'disabled')
        if ready and not self.busy:self.status.set('Ready to play.' if state.get('ai_check') else 'Setup complete. Select a device and run Test AI.')

    def work(self,name,fn):
        if self.busy:return
        self.busy=True;self.task=name;self.cancel.clear();self.refresh()
        def worker():
            try:self.events.put(('done',fn()))
            except Exception as e:
                import traceback
                with (self.install.data/'setup.log').open('a',encoding='utf-8') as f:f.write(traceback.format_exc()+'\n')
                self.events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def progress_event(self,text,fraction):self.events.put(('progress',(text,fraction)))

    def setup(self):
        rom,model=self.rom.get().strip(),self.model.get().strip()
        self.work('setup',lambda:self.install.setup(rom or None,model or None,self.progress_event,self.cancel))

    def test_ai(self):self.work('test',lambda:self.install.test_ai(self.progress_event))

    def device_changed(self,event):
        i=self.device.current()
        if i>=0:self.install.select_device(self.install.state()['devices'][i]['id']);self.refresh()

    def start(self):
        def run():
            self.session=Session(self.install)
            try:self.session.start()
            except Exception:self.session=None;raise
            return None
        self.work('play',run)

    def copy_bridge(self):
        self.root.clipboard_clear();self.root.clipboard_append(str(self.session.script));self.link.set('Bridge path copied. Paste it into mGBA’s Load script dialog.')

    def open_dashboard(self):
        if self.session:webbrowser.open(f'http://127.0.0.1:{self.session.dashboard_port}')

    def make_backup(self):
        self.work('backup',lambda:str(self.install.backup()))

    def change_data(self):
        chosen=filedialog.askdirectory(title='Choose a persistent Metamorphosis data folder')
        if not chosen:return
        try:
            install=Installation(chosen)
            if install.data==self.install.data:return
            lock=DataLock(install.data/'launcher.lock')
            if self.session:self.session.close();self.session=None
            self.lock.close();self.lock=lock;self.install=install;self.location.configure(text=str(install.data))
            if getattr(sys,'frozen',False):
                (Path(sys.executable).parent/'portable-settings.json').write_text(json.dumps({'data':str(install.data)}))
            self.refresh()
        except Exception as e:messagebox.showerror('Data folder',str(e))

    def help(self):
        path=self.install.assets/'PLAYER_GUIDE.txt';os.startfile(path)

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress':
                    text,fraction=value;self.status.set(text)
                    if fraction is None:self.progress.configure(mode='indeterminate');self.progress.start(15)
                    else:self.progress.stop();self.progress.configure(mode='determinate',value=100*fraction)
                else:
                    self.busy=False;self.progress.stop();self.refresh()
                    if kind=='error':self.status.set(value);messagebox.showerror('Metamorphosis',value)
                    elif self.task=='backup':messagebox.showinfo('Backup created',value)
        except queue.Empty:pass
        if self.session and not self.busy:
            if self.session.game and self.session.game.poll() is not None:
                self.session.close();self.session=None;self.link.set('Game closed. Your data stays in the data folder.');self.refresh()
            else:
                try:
                    status=self.session.status()
                    self.link.set('Connected — metamorphosis is ready.' if status.get('connected') else 'Waiting for the Lua bridge. Load the script in mGBA using the copied path.')
                    if status.get('error'):self.link.set('Companion: '+status['error'])
                except (OSError,ValueError):self.link.set('Companion unavailable. Save and close mGBA, then check companion.log.')
        self.root.after(1000,self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Work in progress','Wait for this operation to finish. Downloads can be paused with Pause download.');return
        try:
            if self.session:self.session.close()
        except RuntimeError as e:messagebox.showinfo('Game is running',str(e));return
        self.lock.close();self.root.destroy()

    def run(self):self.root.mainloop()
