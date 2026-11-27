"""Tests de preparacion de datos del pipeline VIGENTE.

Reducido el 27 nov 2026. Este fichero probaba ademas `data_splitting`,
`data_shuffling`, `fetch_parent_proteins_fastas` y `check_group_splits`, cuyos
scripts se borraron en la poda del commit b986ee1 sin actualizar los tests: la
suite llevaba desde entonces con 15 de 18 tests en error, no por regresiones
sino por probar codigo inexistente. Se conservan las dos clases cuyas
dependencias siguen vivas.
"""
import unittest

from data_pipeline.scripts.data_augmentation.augment_blosum62 import (
    cargar_blosum62,
    mejor_sustituto,
    variantes_repo,
)


class AugmentationTests(unittest.TestCase):
    """Metodo `repo` de augment_blosum62: determinista, una variante por posicion.

    Sustituye a los tests de generate_blosum62_variants.py, retirado el 27 nov
    2026. La logica es la misma; lo que cambia es que `variantes_repo` NO
    incluye el original en su salida (lo escribe el llamador como fila 0) y
    devuelve ademas la posicion mutada y los dos aminoacidos, para que la
    relacion variante-original sea verificable sin realinear.
    """

    @classmethod
    def setUpClass(cls):
        cls.best = mejor_sustituto(cargar_blosum62())

    def test_known_highest_scoring_blosum_substitutions(self):
        self.assertEqual(
            [v[0] for v in variantes_repo('ADW', self.best)],
            ['SDW', 'AEW', 'ADY'],
        )

    def test_one_substitution_per_position_and_metadata_matches(self):
        sequence = 'ACDEFGHIKLMNPQRSTVWYACDEF'
        variants = variantes_repo(sequence, self.best)
        self.assertEqual(len(variants), 25)
        for position, (variant, pos, aa0, aa1, _) in enumerate(variants):
            difieren = [i for i, (a, b) in enumerate(zip(sequence, variant)) if a != b]
            self.assertEqual(difieren, [position])
            self.assertEqual(pos, position)
            self.assertEqual(aa0, sequence[position])
            self.assertEqual(aa1, variant[position])
            self.assertEqual(len(variant), 25)
            self.assertTrue(set(variant) <= set('ACDEFGHIKLMNPQRSTVWY'))

    def test_substitution_never_returns_the_same_aminoacid(self):
        for aa in 'ACDEFGHIKLMNPQRSTVWY':
            self.assertNotEqual(self.best[aa], aa)



class ClassificationTests(unittest.TestCase):
    def test_epitope_match_uses_one_based_exact_coordinates(self):
        from data_pipeline.scripts.data_classification.epitope_classification import validate_exact_match
        protein = 'ACDEFGHIKLMNPQRSTVWY'
        self.assertTrue(validate_exact_match(protein, 'DEF', 3, 5))
        for start, end in [(4, 6), (0, 2), (19, 21)]:
            self.assertFalse(validate_exact_match(protein, 'DEF', start, end))

    def test_epitopes_at_both_window_boundaries_match_exactly(self):
        from data_pipeline.scripts.data_classification.epitope_classification import validate_exact_match
        window = 'ACDEFGHIKLMNPQRSTVWYACDEF'
        self.assertTrue(validate_exact_match(window, 'ACD', 1, 3))
        self.assertTrue(validate_exact_match(window, 'DEF', 23, 25))
        self.assertTrue(validate_exact_match(window, window, 1, 25))

    def test_position_score_is_centered_and_symmetric(self):
        from data_pipeline.scripts.data_classification.epitope_classification import compute_epitope_position_score
        centered = compute_epitope_position_score(1, 25, 10, 16, 25)
        left = compute_epitope_position_score(1, 25, 1, 7, 25)
        right = compute_epitope_position_score(1, 25, 19, 25, 25)
        self.assertEqual(centered, 0)
        self.assertLess(left, 0)
        self.assertAlmostEqual(left, -right)
