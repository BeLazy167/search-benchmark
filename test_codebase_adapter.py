"""Public fixtures for codebase-memory 0.12 compact JSON."""
import unittest
from codebase_bench import expand_groups


class CompactResultsTests(unittest.TestCase):
    def test_file_groups_preserve_qualified_symbols(self):
        table = {'cols': ['name', 'label'], 'groups': [
            {'file': 'example.py', 'qn_prefix': 'example', 'rows': [['handle', 'Function']]},
            {'file': 'other.py', 'qn_prefix': '', 'rows': [['root', 'Function']]},
        ]}
        nodes = expand_groups(table)
        self.assertEqual(nodes[0]['qualified_name'], 'example.handle')
        self.assertEqual(nodes[0]['file_path'], 'example.py')
        self.assertEqual(nodes[1]['qualified_name'], 'root')

    def test_callers_do_not_invent_file_paths(self):
        nodes = expand_groups({'cols': ['name', 'hop', 'test'], 'groups': [
            {'qn_prefix': 'example', 'rows': [['caller', 1, False]]},
        ]})
        self.assertEqual(nodes[0]['qualified_name'], 'example.caller')
        self.assertNotIn('file_path', nodes[0])

    def test_malformed_row_is_rejected(self):
        with self.assertRaises(ValueError):
            expand_groups({'cols': ['name'], 'groups': [
                {'qn_prefix': '', 'rows': [['one', 'extra']]},
            ]})
