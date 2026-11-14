import importlib.util
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('configure_maps', BASE / 'configure_maps.py')
maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maps)


class MapConfiguration(unittest.TestCase):
    def test_pending_coordinates_are_optional_and_do_not_consume_comments(self):
        values = maps.credentials('NEXT_PUBLIC_KAKAO_MAP_KEY=' + 'a' * 32 + '\nJUSO_SEARCH_API_KEY=example%2B==\nJUSO_COORD_API_KEY=\n# approval pending\n')
        self.assertEqual(values['JUSO_COORD_API_KEY'], '')
        self.assertEqual(values['JUSO_SEARCH_API_KEY'], 'example%2B==')

    def test_blank_search_key_and_interpolated_values_are_rejected(self):
        for value in ('', '${SECRET}', 'bad\\value'):
            with self.assertRaises(ValueError):
                maps.credentials('NEXT_PUBLIC_KAKAO_MAP_KEY=' + 'a' * 32 + '\nJUSO_SEARCH_API_KEY=' + value)

    def test_merge_preserves_oauth_budgets_and_coordinate_key(self):
        original = 'GOOGLE_CLIENT_SECRET=existing\nEXTRACTION_PUBLICATION_MODE=verified\nJUSO_COORD_API_KEY=approved-existing\n'
        merged = maps.merge(original, {'JUSO_SEARCH_API_KEY': 'example'})
        self.assertTrue(merged.startswith(original))
