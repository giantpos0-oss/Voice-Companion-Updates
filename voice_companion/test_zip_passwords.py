"""Will, November 4, 2026: password-protected zips. Alt+U asks for the password of a locked zip,
of either kind (the older ZipCrypto, or WinZip AES from 7-Zip and WinRAR). Alt+Shift+Z makes a zip
locked with WinZip AES-256. Passwords are typed in a private box: never spoken or written down."""
import tempfile
import unittest
import zipfile
import zlib
import struct
from pathlib import Path

import file_tools
import zip_crypto
from file_manager import FileManager
from test_file_manager import FakeFiles, settle

# A WinZip AES-256 zip made by another program (from pyzipper's tests, "known good"), password
# "test", holding test.txt: "This is a test file for AES encryption."
KNOWN_AES = (
    b'PK\x03\x04\x14\x00\x01\x00c\x00\x00\x00!\x00&[<ZC\x00\x00\x00'
    b'\'\x00\x00\x00\x08\x00\x0b\x00test.txt\x01\x99\x07\x00\x01\x00AE'
    b'\x03\x00\x00\xe5G\xf2Z"[\xd0\xce\x96\xb7\xb3\xf6\x85\x8f|\x05'
    b'\xa9\xdaBGz:!\xde\xa6\x9a\xb7\x81A\x8e\x82\xfd)6|\x84\xf93\x0ecU'
    b'\xa7\x07v\xe19\x18A\x94GmQ\xc5Y\x12\xb0\x05=\xbb\xd2\x9bi\x873'
    b'\xb9\xbd\xf1PK\x01\x02\x14\x03\x14\x00\x01\x00c\x00\x00\x00!\x00'
    b'&[<ZC\x00\x00\x00\'\x00\x00\x00\x08\x00\x0b\x00\x00\x00\x00\x00'
    b'\x00\x00\x00\x00\x80\x01\x00\x00\x00\x00test.txt\x01\x99\x07\x00'
    b'\x01\x00AE\x03\x00\x00PK\x05\x06\x00\x00\x00\x00\x01\x00\x01\x00'
    b'A\x00\x00\x00t\x00\x00\x00\x00\x00')


def zipcrypto_zip(target, name, data, password):
    """An old-style (ZipCrypto) locked zip, as File Explorer and older tools make. Python can read
    these but not write them, so the test writes one with the published PKWARE algorithm."""
    crc_table = [0] * 256
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        crc_table[i] = c
    keys = [0x12345678, 0x23456789, 0x34567890]
    def update(byte):
        keys[0] = (keys[0] >> 8) ^ crc_table[(keys[0] ^ byte) & 0xFF]
        keys[1] = ((keys[1] + (keys[0] & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
        keys[2] = (keys[2] >> 8) ^ crc_table[(keys[2] ^ (keys[1] >> 24)) & 0xFF]
    def encrypt(plain):
        out = bytearray()
        for byte in plain:
            temp = (keys[2] | 2) & 0xFFFF
            out.append(byte ^ ((temp * (temp ^ 1)) >> 8) & 0xFF)
            update(byte)
        return bytes(out)
    for byte in password.encode():
        update(byte)
    crc = zlib.crc32(data)
    header = bytes(11) + bytes([crc >> 24 & 0xFF])
    body = encrypt(header) + encrypt(data)
    encoded = name.encode()
    local = struct.pack('<4s5H3L2H', b'PK\x03\x04', 20, 1, 0, 0, 0x21, crc, len(body), len(data), len(encoded), 0) + encoded
    central = struct.pack('<4s6H3L5H2L', b'PK\x01\x02', 20, 20, 1, 0, 0, 0x21, crc, len(body), len(data), len(encoded), 0, 0, 0, 0, 0x20, 0) + encoded
    end = struct.pack('<4s4H2LH', b'PK\x05\x06', 0, 0, 1, 1, len(central), len(local) + len(body), 0)
    Path(target).write_bytes(local + body + central + end)


class ZipPasswordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'letter.txt').write_text('Dear Bob. ' * 500)
        (self.root / 'Photos').mkdir()
        (self.root / 'Photos' / 'cat.jpg').write_bytes(bytes(range(256)) * 300)

    def test_a_zip_made_by_another_program_with_aes_opens(self):
        (self.root / 'known.zip').write_bytes(KNOWN_AES)
        with self.assertRaises(file_tools.NeedsPassword):
            file_tools.unzip_file(self.root / 'known.zip')
        with self.assertRaises(zip_crypto.WrongPassword):
            file_tools.unzip_file(self.root / 'known.zip', 'wrong')
        folder, count = file_tools.unzip_file(self.root / 'known.zip', 'test')
        self.assertEqual((folder / 'test.txt').read_text(), 'This is a test file for AES encryption.')
        self.assertEqual(count, 1)

    def test_an_old_style_locked_zip_opens(self):
        zipcrypto_zip(self.root / 'old.zip', 'note.txt', b'Old kind of lock.', 'pass word')
        with self.assertRaises(file_tools.NeedsPassword):
            file_tools.unzip_file(self.root / 'old.zip')
        with self.assertRaises(zip_crypto.WrongPassword):
            file_tools.unzip_file(self.root / 'old.zip', 'nope')
        folder, _ = file_tools.unzip_file(self.root / 'old.zip', 'pass word')
        self.assertEqual((folder / 'note.txt').read_bytes(), b'Old kind of lock.')

    def test_password_zips_are_aes_256_and_open_again(self):
        target = self.root / 'Locked.zip'
        self.assertEqual(file_tools.make_zip([self.root / 'letter.txt', self.root / 'Photos'], target, 'p@ss'), 2)
        with zipfile.ZipFile(target) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    self.assertTrue(info.flag_bits & 1)
                    self.assertEqual(zip_crypto.aes_details(info), (3, 8))   # AES-256, deflated
                    with self.assertRaises(NotImplementedError):
                        archive.read(info, pwd=b'p@ss')   # not readable as an unlocked or old-style zip
        self.assertNotIn(b'Dear Bob', target.read_bytes())
        folder, count = file_tools.unzip_file(target, 'p@ss')
        self.assertEqual(count, 2)
        self.assertEqual((folder / 'letter.txt').read_text(), 'Dear Bob. ' * 500)
        self.assertEqual((folder / 'Photos' / 'cat.jpg').read_bytes(), bytes(range(256)) * 300)

    def test_a_tampered_zip_is_refused(self):
        target = self.root / 'Locked.zip'
        file_tools.make_zip([self.root / 'letter.txt'], target, 'pw')
        data = bytearray(target.read_bytes())
        data[80] ^= 0xFF
        target.write_bytes(bytes(data))
        with self.assertRaisesRegex(ValueError, 'damaged'):
            file_tools.unzip_file(target, 'pw')
        self.assertEqual([p.name for p in self.root.iterdir() if 'unzipping' in p.name], [])


class FileManagerPasswordTests(ZipPasswordTests.__base__):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'letter.txt').write_text('Dear Bob.')
        self.fm = FileManager(FakeFiles(self.root))
        self.fm.refresh(); settle(self.fm)
        self.fm.command('enter'); settle(self.fm)

    def test_alt_shift_z_asks_for_the_password_twice_and_locks_the_zip(self):
        self.fm.choose('letter.txt')
        self.assertTrue(self.fm.command('zip with password').startswith('Zip with a password: letter.txt.'))
        self.assertIn('Type a password', self.fm.command('Private'))
        self.assertTrue(self.fm.private_step())
        self.assertIn('typed, not spoken', self.fm.command('my secret words'))
        self.assertIn('same password again', self.fm.secret('one'))
        self.assertIn('not the same', self.fm.secret('two'))
        self.fm.secret('one')
        said = self.fm.secret('one') + ' ' + settle(self.fm)
        self.assertIn('Zipped 1 item into Private.zip, locked with a password.', said)
        self.assertIsNone(self.fm.zip_secret)
        with self.assertRaises(file_tools.NeedsPassword):
            file_tools.unzip_file(self.root / 'Private.zip')

    def test_alt_u_asks_for_the_password_and_again_when_wrong(self):
        (self.root / 'known.zip').write_bytes(KNOWN_AES)
        self.fm.command('refresh'); settle(self.fm)
        self.fm.choose('known.zip')
        said = self.fm.command('unzip') + ' ' + settle(self.fm)
        self.assertIn('known.zip is locked with a password', said)
        self.assertEqual(self.fm.pending[0], 'unzip password')
        said = self.fm.secret('wrong') + ' ' + settle(self.fm)
        self.assertIn('That password does not open known.zip', said)
        said = self.fm.secret('test') + ' ' + settle(self.fm)
        self.assertIn('Unzipped known.zip into the known folder', said)
        self.assertTrue((self.root / 'known' / 'test.txt').exists())

    def test_the_password_box_is_private_and_kept_out_of_the_transcript(self):
        import companion
        import speech_transcript
        self.assertEqual(speech_transcript.key_label(('file_secret', 'hunter2')), 'private entry [hidden]')
        self.fm.choose('letter.txt'); self.fm.command('zip with password'); self.fm.command('x')
        from unittest.mock import patch
        with patch.object(companion, 'FILE_MANAGER', self.fm):
            context = companion.app_context('files')
        self.assertTrue(context['file_private'])
        self.assertEqual(context['file_input_label'], 'Password for the zip (private)')
        self.assertEqual(companion.navigation_key('Alt+Shift+Z', 'files'), 'zip with password')


if __name__ == '__main__':
    unittest.main()
