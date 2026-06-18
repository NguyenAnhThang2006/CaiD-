import unittest
import sys
import os

# Ensure backend path is importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from pfig_core import PFIGGraph

class TestPFIGLogic(unittest.TestCase):
    def setUp(self):
        self.pfig = PFIGGraph()

    def test_graph_initialization(self):
        """Verifies that all nodes and edges from the case study are correctly loaded."""
        self.assertEqual(len(self.pfig.G.nodes), 11)
        self.assertEqual(len(self.pfig.G.edges), 15)
        
        # Test coordinates presence
        for node in self.pfig.G.nodes:
            self.assertIn("coords", self.pfig.G.nodes[node])

    def test_fuzzy_sum_constraints(self):
        """Verifies that the sum of fuzzy memberships (P + N + n) is <= 1.0."""
        # Check all nodes
        for node in self.pfig.G.nodes:
            attrs = self.pfig.G.nodes[node]
            self.assertLessEqual(attrs["P"] + attrs["N"] + attrs["n"], 1.01) # allow minor floating precision
            
        # Check all edges
        for u, v in self.pfig.G.edges:
            attrs = self.pfig.G[u][v]
            self.assertLessEqual(attrs["P"] + attrs["N"] + attrs["n"], 1.01)

    def test_incidence_constraints(self):
        """Verifies that incidence values (M) satisfy Definition 2.1 min-max constraints."""
        for u, v in self.pfig.G.edges:
            edge_name = tuple(sorted([u, v]))
            edge_attr = self.pfig.G[u][v]
            
            for node in [u, v]:
                node_attr = self.pfig.G.nodes[node]
                inc = self.pfig.incidence_data.get((node, edge_name))
                
                self.assertIsNotNone(inc)
                # PM(e, ef) <= min(PK(e), PL(ef))
                self.assertLessEqual(inc[0], min(node_attr["P"], edge_attr["P"]) + 0.01)
                # NM(e, ef) <= min(NK(e), NL(ef))
                self.assertLessEqual(inc[1], min(node_attr["N"], edge_attr["N"]) + 0.01)
                # nM(e, ef) <= max(nK(e), nL(ef))
                self.assertLessEqual(inc[2], max(node_attr["n"], edge_attr["n"]) + 0.01)
                
                # Check sum constraint
                self.assertLessEqual(sum(inc), 1.01)

    def test_path_intensity_accumulation(self):
        """Verifies that path intensity calculation matches the manual math details (bottleneck principle)."""
        # We test a simple path: My Dinh -> Nguyen Chi Thanh
        path = ["My Dinh", "Nguyen Chi Thanh"]
        intensity_data = self.pfig.get_path_intensity(path)
        
        # Verify steps and result structure
        self.assertEqual(len(intensity_data["steps"]), 1)
        final_intensity = intensity_data["intensity"]
        
        # Positive intensity must be min of steps, negative must be max
        step_fuzzy = intensity_data["steps"][0]["step_fuzzy"]
        self.assertEqual(final_intensity[0], step_fuzzy[0])
        self.assertEqual(final_intensity[1], step_fuzzy[1])
        self.assertEqual(final_intensity[2], step_fuzzy[2])

    def test_modified_dijkstra(self):
        """Verifies that modified PFIG Dijkstra calculates route successfully."""
        source = "My Dinh"
        target = "HUST"
        
        # Compute PFIG route
        path, dist, cost = self.pfig.compute_pfig_route(source, target, alpha=0.5, beta=0.3, gamma=0.2)
        
        self.assertIsNotNone(path)
        self.assertEqual(path[0], source)
        self.assertEqual(path[-1], target)
        self.assertGreater(dist, 0.0)
        self.assertGreater(cost, 0.0)

    def test_structural_vulnerabilities(self):
        """Verifies that the structural bridge/cut-pair finder doesn't crash and returns lists."""
        source = "My Dinh"
        target = "HUST"
        
        bridges, cut_pairs = self.pfig.identify_structural_vulnerabilities(source, target)
        self.assertIsInstance(bridges, list)
        self.assertIsInstance(cut_pairs, list)

if __name__ == '__main__':
    unittest.main()
