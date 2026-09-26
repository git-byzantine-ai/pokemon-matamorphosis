import unittest
from PIL import Image, ImageDraw
from companion.sprites import INK, fit, pixel_finish, encode_pair, validate


class PixelArtTests(unittest.TestCase):
    def test_thin_appendages_survive_and_detached_noise_is_removed(self):
        im = Image.new('RGBA',(64,64))
        d = ImageDraw.Draw(im)
        d.rectangle((20,20,40,50),fill=(220,180,60,255))
        d.line((22,20,22,7),fill=(220,180,60,255),width=1)
        d.point((3,3),fill=(170,170,170,255))
        out = pixel_finish(im)
        self.assertEqual(out.getpixel((3,3))[3],0)
        self.assertEqual(out.getpixel((22,7)),im.getpixel((22,7)))
        self.assertEqual(out.getpixel((21,7)),(*INK,255))
        self.assertEqual(out.getpixel((20,7))[3],0)
        self.assertEqual(out.getpixel((30,30)),im.getpixel((30,30)))

    def test_final_export_is_binary_alpha_shared_palette_and_deterministic(self):
        views = []
        for base in (40,100):
            im = Image.new('RGBA',(512,512),'white')
            d = ImageDraw.Draw(im)
            for y in range(70,450):
                d.line((160,y,350,y), fill=(base+y//4,100+y//8,60,255))
            views.append(pixel_finish(fit(im)))
        data, previews = encode_pair(*views)
        validate(data)
        self.assertEqual(data,encode_pair(*views)[0])
        colors = {p[:3] for im in previews for p in im.getdata() if p[3]}
        self.assertLessEqual(len(colors),15)
        self.assertIn((32,32,49),colors)  # Reserved ink snapped to RGB555.
        for im in previews:
            self.assertEqual(set(im.getchannel('A').getdata()),{0,255})
            x0,y0,x1,y1 = im.getbbox()
            self.assertGreater(x0,0)
            self.assertGreater(y0,0)
            self.assertLess(x1,64)
            self.assertLess(y1,64)


if __name__ == '__main__':
    unittest.main()
