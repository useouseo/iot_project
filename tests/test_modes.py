"""Festival type is selected at creation; public links stay pinned to a festival."""
import unittest
from server import Store,Problem,festival_url

class FestivalModeTests(unittest.TestCase):
    def test_type_cannot_be_switched_after_creation(self):
        store=Store.__new__(Store)
        for mode in ('indoor','outdoor','bad',None):
            with self.subTest(mode=mode),self.assertRaises(Problem) as error:store.set_map_mode(mode)
            self.assertEqual(error.exception.status,409)
    def test_qr_replaces_old_path_and_keeps_festival_identity(self):
        first=dict(public_id='festival-one');second=dict(public_id='festival-two')
        self.assertEqual(festival_url('https://festival.example.org/old?event=4#part',first),'https://festival.example.org/f/festival-one')
        self.assertNotEqual(festival_url('https://festival.example.org',first),festival_url('https://festival.example.org',second))
    def test_absent_public_base_has_no_fabricated_url(self):
        self.assertEqual(festival_url('',dict(public_id='festival-one')),'')
