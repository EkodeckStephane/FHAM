# Étape 1bis — Résultats F2 (BOWS2-A/B)

**Date : 17 novembre 2026.** Analyse exploratoire conforme à la sélection gelée avant BOWS2-B. L’environnement de calcul était Python 3.13.5, OpenCV 4.12.0, NumPy 2.2.6 et SciPy 1.17.1. Le profil retenu par le dépistage précédent est L=12, avec B=2.

## Exécution

- **A :** 100 couvertures, 8 messages par couverture (quatre familles, 100 et 200 octets source, indice 00), 16 configurations S0–S4q, cinq transformations de validation et chemins P0–P3. Temps : 491 s.
- **B :** 200 couvertures, 24 messages par couverture (indices 00–02), les trois configurations sélectionnées sur A et S0 comme témoin. Temps : 819 s.
- La sélection A a été commitée avant l'ouverture de B (`107e998`). Les pixels du split C n'ont pas été ouverts.
- Les sorties brutes consolidées sont archivées en CSV compressés au niveau de l'étape; les lots de calcul par couverture restent récupérables localement dans `A/` et `B/`. Les manifestes d'exécution et les sommes SHA-256 sont conservés avec l'archive.

## Sélection issue de A

Huit configurations satisfaisaient les deux critères d'admissibilité : faisabilité au moins 95 % sur les messages de 100 octets source et D₁ moyen au plus cinq fois celui de S0. La sélection gelée est :

| Configuration | Justesse P3 moyenne sur 5 transformations | Faisabilité à 100 octets | D₁ / D₁(S0) |
|---|---:|---:|---:|
| S2, λ=0,50 | 69,12 % | 100 % | 2,33 |
| S2, λ=0,90 | 67,46 % | 100 % | 1,00 |
| S2, λ=0,75 | 67,46 % | 100 % | 1,00 |
| S0, référence ajoutée à B | — | — | — |

S2, λ=0,25 obtenait la meilleure justesse exploratoire (76,81 %), mais son D₁ était 15,41 fois celui de S0 : elle ne satisfaisait donc pas le critère de coût. S4q n'a pas produit de configuration admissible combinant faisabilité et coût D₁.

## Résultats B et barrières

Tous les cas retenus étaient faisables à 100 octets source. Les justesses ci-dessous sont des fractions moyennes d'octets récupérés sous l'inverse oracle P3, d'abord moyennées par couverture. P3 est une borne de diagnostic qui suppose la transformation géométrique connue; ce n'est pas une performance du récepteur en conditions ordinaires.

| Configuration | JPEG 75 | Bruit σ=2 | Rotation +1° P3 | Recadrage 5 % P3 |
|---|---:|---:|---:|---:|
| S0 | 22,64 % [20,73; 24,65] | 31,24 % [28,55; 34,09] | 51,61 % | 35,73 % |
| S2, λ=0,50 | 56,42 % [54,82; 57,97] | 69,66 % [67,55; 71,68] | 81,66 % | 72,08 % |
| S2, λ=0,75 | 54,61 % [52,98; 56,20] | 67,79 % [65,63; 69,84] | 80,27 % | 70,57 % |
| S2, λ=0,90 | 54,61 % [52,95; 56,25] | 67,79 % [65,65; 69,84] | 80,27 % | 70,57 % |

Les intervalles entre crochets sont des IC bootstrap à 95 %, 10 000 réplications, avec la couverture comme unité de rééchantillonnage.

**G-A1 est rouge.** Aucune configuration n'approche le seuil de 95 % sous JPEG 75 et bruit σ=2. Même la meilleure, S2 λ=0,50, atteint 56,42 % sous JPEG (borne basse 54,82 %) et 69,66 % sous bruit (borne basse 67,55 %). Cela déclenche l'arrêt prévu avant les étapes F3/F4 et avant toute ouverture du split C.

**G-A2 est positif.** Par rapport à S0, S2 λ=0,50 améliore la justesse P3 de 30,05 points sous rotation (IC [29,06; 31,09]) et de 36,35 points sous recadrage (IC [35,44; 37,24]). Les autres configurations S2 testées ont également des IC strictement positifs. Cette amélioration partielle ne lève pas le verrou G-A1.

## Synchronisation et récupération exacte

Les résultats P3 surestiment le récepteur puisqu'ils utilisent l'inverse géométrique connu. Avec S2 λ=0,50, la justesse moyenne sous rotation est 25,95 % en coordonnées fixes P1, 75,63 % après ORB/RANSAC P2 et 81,66 % sous l'oracle P3. Sous recadrage, elle vaut 3,25 % (P1), 52,69 % (P2) et 72,08 % (P3).

La récupération exacte reste rare malgré les gains de justesse : pour S2 λ=0,50, les taux de messages exactement récupérés sont 0,23 % sous JPEG, 1,81 % sous bruit, 2,71 % sous rotation P2 contre 4,25 % sous P3, et 0,10 % sous recadrage P2 contre 1,29 % sous P3. La robustesse partielle ne doit donc pas être présentée comme une récupération fiable de messages complets.

## Décision selon le protocole

G-A1 rouge impose l'arrêt de 1bis au point prévu. Les résultats ne justifient pas l'ouverture de BOWS2-C, ni le passage aux expériences F3 (signalement) et F4 (Reed–Solomon) dans cette campagne. La suite prévue est l'étape 1ter : travailler le descripteur (marge/hystérésis ou autre représentation), sur de nouvelles données de développement, avant de définir un nouveau protocole. Les gains de S2 sous perturbations géométriques sont réels dans cette grille, mais ne compensent pas l'insuffisance photométrique ni le faible taux de récupération exacte.

## Artefacts

- `A_configuration_summary.csv`, `A_cover_configuration_metrics.csv`, `A_cover_transform_metrics.csv`
- `A_raw_assignments.csv.gz`, `A_raw_recovery.csv.gz`, `A_raw_feasibility.csv.gz`, `A_run.json`
- `frozen_selection_A.json`
- `B_configuration_summary.csv`, `B_transform_summary.csv`, `B_all_path_summary.csv`, `B_family_path_summary.csv`
- `B_cover_configuration_metrics.csv`, `B_cover_transform_metrics.csv`
- `B_raw_assignments.csv.gz`, `B_raw_recovery.csv.gz`, `B_raw_feasibility.csv.gz`, `B_run.json`
- `B_G_A1_cells.csv`, `B_G_A1_configurations.csv`, `B_G_A2_paired_deltas.csv`, `B_gate_verdict.json`
- `scripts/run_step1bis_stability.py`, `scripts/summarize_step1bis_stability_A.py`, `scripts/summarize_step1bis_stability_B.py`
- `archive_sha256.json` fournit les empreintes des artefacts consolidés.
