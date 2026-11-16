# État de l’étape 1 — stabilité par position

**Branche :** `revision/position-stability-2026-11-15`
**Date :** 16 novembre 2026
**Périmètre :** étapes 0 et 1 uniquement; le test scellé n’a pas encore été évalué.

## Reproduction et pilote D0

La porte de reproduction des tableaux 8, 9 et 34 est franchie : l’écart maximal par rapport aux valeurs publiées est de 0,048 point de pourcentage, inférieur à la tolérance de 1 point.

Le pilote D0 corrigé utilise 20 couvertures LFW-dev, dont 19 affectations faisables. Il applique ORB/RANSAC à la rotation, au recadrage-restauration et à la réduction-restauration. Un recalage en échec compte comme un échec P2. La première sortie, qui ne recalait pas le redimensionnement, est conservée dans `results/stability_step1/pilot_d0_pre_resize_registration/` et n’est pas utilisée.

| Transformation | P1, coordonnées fixes | P2, ORB/RANSAC | P3, inverse oracle |
|---|---:|---:|---:|
| Rotation +1° | 14,69 % | 16,89 % | 72,70 % |
| Recadrage 5 % | 1,54 % | 11,18 % | 62,06 % |
| Réduction-restauration ×0,8 | 53,07 % | 32,46 % | 53,07 % |

Aucun message du pilote n’est entièrement récupéré après transformation. Pour ×0,8, le recalage P2 réduit la justesse par rapport à P1; l’inverse oracle ne change pas la grille restaurée.

L’écart-type apparié P2−P1 le plus élevé concerne ×0,8. Le calcul prévu par le protocole donne **N = 201**. LFW-val reste à 100 images pour sélectionner les paramètres; le test final est dimensionné à 201 images éligibles par corpus afin que BOSSBase et COCO aient chacun cet effectif.

## Développement et sélection LFW-val

Les moyennes de stabilité par position sont S1 = 0,3850, S2 = 0,2877 et S3 = 0,0818. Elles décrivent le score des positions et ne sont pas des taux de récupération.

La validation couvre 100 images et 2 400 affectations par configuration. S0–S3 atteignent 95,29 % de faisabilité (2 287/2 400; IC Wilson 95 % : 94,37–96,07 %). S4 n’a aucune affectation faisable pour les seuils τ testés.

La règle préétablie sélectionne **S3, λ = 0,5** : justesse conditionnelle moyenne de 20,90 %, justesse sans condition de 20,46 %, D₁ moyen 8,66, soit 2,12 fois S0. Seules S2 et S3 à λ = 0,5 sont à moins d’une erreur-type du meilleur résultat; le plus petit D₁ retient S3.

| Transformation et chemin primaire | Justesse conditionnelle | IC 95 % par grappes | Récupération exacte |
|---|---:|---:|---:|
| JPEG 75, P1 | 15,50 % | 13,30–17,75 % | 0/2 400 |
| Bruit σ=2, P1 | 9,31 % | 8,01–10,66 % | 0/2 400 |
| Rotation +1°, P2 | 24,51 % | 19,62–29,49 % | 0/2 400 |
| Recadrage 5 %, P2 | 17,34 % | 13,63–21,14 % | 0/2 400 |
| Réduction-restauration ×0,8, P2 | 37,84 % | 31,62–44,14 % | 5/2 400 |

Le recalage ORB/RANSAC réussit sur 57/100 couvertures pour la rotation, 54/100 pour le recadrage et 60/100 pour le redimensionnement. Les moyennes de correspondances / inliers RANSAC sont respectivement 68,97/51,34, 34,10/22,24 et 94,35/93,63.

## Signalement récepteur R-a

Le seuil retenu sur LFW-val est `z_flag = 0,5`. Sur les chemins primaires, le signalement marque 97,59 % des symboles comme effacements et laisse 0,155 % d’erreurs silencieuses. Le rendement optimiste calculé est **R_max = 0,0210** (2,10 %); il est très inférieur au seuil rouge de 0,40 du protocole.

| Transformation | R_max | IC 95 % par grappes |
|---|---:|---:|
| JPEG 75, P1 | 0,0219 | 0,0180–0,0257 |
| Bruit σ=2, P1 | 0,0047 | 0,0033–0,0063 |
| Rotation +1°, P2 | 0,0259 | 0,0197–0,0325 |
| Recadrage 5 %, P2 | 0,0179 | 0,0132–0,0230 |
| Réduction-restauration ×0,8, P2 | 0,0347 | 0,0282–0,0415 |

Le R-a ne rend donc pas un code correcteur viable dans les conditions mesurées. Le test scellé reste néanmoins prévu par le protocole; aucune image de test n’a été décodée à ce stade.

## Inventaire du test scellé

Les 400 candidats BOSSBase et 400 candidats COCO ont été reliés au manifeste source. Les SHA-256 des PNG dérivés correspondent tous au manifeste. L’audit d’identifiants et de SHA-256 a exclu 81 candidats BOSSBase et 159 COCO déjà employés dans les résultats FHAM conservés; il reste 319 et 241 candidats éligibles. Une sélection déterministe en retient 201 par corpus. **Seul leur hash a été calculé; aucun pixel n’a été décodé ni analysé.**

La configuration S3/λ=0,5 et le seuil R-a 0,5 sont maintenant fixés par LFW-val. Le code, la configuration et les manifestes doivent être commités avant l’unique exécution scellée. Le résultat déterminera la décision finale de l’étape 1; les résultats LFW-val actuels placent déjà toutes les transformations en zone rouge.

## Fichiers de résultats principaux

- `results/stability_step1/reproduction_gate.json`
- `results/stability_step1/pilot_d0_summary.csv`
- `results/stability_step1/pilot_sample_size.json`
- `results/stability_step1/dev_stability_summary.csv`
- `results/stability_step1/validation_config_selection.json`
- `results/stability_step1/validation_registration_summary.csv`
- `results/stability_step1/validation_selected_accuracy_ci.csv`
- `results/stability_step1/receiver_validation_selection.json`
- `results/stability_step1/receiver_validation_detailed_summary.csv`
- `results/stability_step1/receiver_validation_rmax_cluster_ci.csv`
- `results/stability_step1/sealed_candidate_manifest.csv`
- `results/stability_step1/sealed_test_selection.csv`
