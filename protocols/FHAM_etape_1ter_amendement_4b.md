# Amendement préexpérience 1ter — branche 4b (18 novembre 2026)

Cet amendement est gelé après la décision G‑T1 rouge (100 couvertures BOWS2-D) et avant toute mesure de descripteur. Il corrige la spécification de C‑Arr4 et fixe la règle de sélection des deux candidats.

## Définitions corrigées

- **C‑spectral** : descripteur original, quatre arrangements et huit comparaisons par emplacement; réestimé avec K=50 par famille pour rendre le classement comparable.
- **C‑moyenne** : scores égaux aux intensités moyennes des neuf sous-blocs 4×4 (L=12); quatre ordres de comparaison du §4.1, huit bits par arrangement.
- **C‑DCT** : DCT‑II orthonormale de chaque sous-bloc 4×4 (L=12); score scalaire `|C00|+|C01|+|C10|`; quatre ordres de comparaison du §4.1, huit bits par arrangement.
- **C‑Arr4** : une empreinte de huit bits par fenêtre 18×18, sous-blocs 6×6, ordre Arr.4 de la méthode Abdulsattar, stride 6. Il s'agit d'un seul arrangement par fenêtre, contrairement aux trois autres descripteurs qui ont quatre arrangements par bloc. Son codebook et sa capacité sont rapportés séparément; sur 256×256, il fournit 40×40=1 600 positions. Les quatre méthodes conservent l'alphabet de symboles 0–255 et le même solveur borné.

## Évaluation et classement

Sur les 100 images D, K=50 perturbations par famille sont tirées selon les plages et exclusions du protocole gelé. Une position est « robuste » si aucun hash ne bascule dans les 50 essais JPEG et les 50 essais bruit. Pour chaque candidat, rapporter les taux par famille, le taux robuste conjoint, le nombre total de positions, le nombre de hashes distincts et la densité par hash.

Classer les quatre descripteurs par moyenne de la fraction robuste par couverture; départager une égalité au sixième décimal par le nombre de couvertures satisfaisant les 12 messages de 100 octets avec B≤8, puis par ordre alphabétique du nom. Retenir les deux premiers, sans consulter E, C ou F. Le classement est exploratoire.

Pour les deux retenus, refaire le plafond C3 sur les 100 images D avec les seules positions robustes, B∈{2,4,8}, les 12 messages primaires de 100 octets et les messages secondaires de 200 octets. Mesurer la récupération sous JPEG 75 et bruit σ=2. Appliquer G‑T1 et G‑T2 exactement comme dans le protocole initial. E reste réservé à la validation de la configuration retenue à l'étape 5; C et F restent fermés jusqu'à l'étape 6.

## Limite d'interprétation

Avec K=50, zéro basculement donne une borne supérieure unilatérale Clopper–Pearson de 5,82 % par famille à 95 %. Le filtre robuste de la branche 4b est donc un criblage exploratoire et n'établit pas une garantie de stabilité à 99 %.
