# État de l’étape 1 — stabilité par position

**Branche :** `revision/position-stability-2026-11-15`
**Date :** 16 novembre 2026
**Périmètre :** étapes 0 et 1 uniquement; le test scellé est terminé. L’étape 2 reste suspendue à l’accord de l’auteur.

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

L’absence de faisabilité S4 concerne la grille absolue τ ∈ {0,5; 0,8; 0,9; 0,95; 0,99}. Elle ne teste pas une sélection par quantile; la grille peut donc être mal adaptée à l’échelle des scores S3. Aucun résultat S4 ne permet de conclure qu’un filtrage des meilleurs emplacements est intrinsèquement infaisable.

La règle préétablie sélectionne **S3, λ = 0,5** : justesse conditionnelle moyenne de 20,90 %, justesse sans condition de 20,46 %, D₁ moyen 8,66, soit 2,12 fois S0. Seules S2 et S3 à λ = 0,5 sont à moins d’une erreur-type du meilleur résultat; le plus petit D₁ retient S3.

| Transformation et chemin primaire | Justesse conditionnelle | IC 95 % par grappes | Récupération exacte |
|---|---:|---:|---:|
| JPEG 75, P1 | 15,50 % | 13,30–17,75 % | 0/2 400 |
| Bruit σ=2, P1 | 9,31 % | 8,01–10,66 % | 0/2 400 |
| Rotation +1°, P2 | 24,51 % | 19,62–29,49 % | 0/2 400 |
| Recadrage 5 %, P2 | 17,34 % | 13,63–21,14 % | 0/2 400 |
| Réduction-restauration ×0,8, P2 | 37,84 % | 31,62–44,14 % | 7/2 400 |

Le recalage ORB/RANSAC réussit sur 57/100 couvertures pour la rotation, 54/100 pour le recadrage et 60/100 pour le redimensionnement. Les moyennes de correspondances / inliers RANSAC sont respectivement 68,97/51,34, 34,10/22,24 et 94,35/93,63.

## Signalement récepteur R-a

Le seuil retenu sur LFW-val est `z_flag = 0,5`. Sur les chemins primaires de LFW-val, le signalement marque 97,59 % des symboles comme effacements et laisse 0,155 % d’erreurs silencieuses. Le rendement R-a de 2,10 % reflète donc principalement le taux d’effacement induit par ce signalement, et non la justesse seule. Il évalue le profil d’effacement testé; il ne démontre pas l’impossibilité générale des codes correcteurs.

| Transformation | R_max | IC 95 % par grappes |
|---|---:|---:|
| JPEG 75, P1 | 0,0219 | 0,0180–0,0257 |
| Bruit σ=2, P1 | 0,0047 | 0,0033–0,0063 |
| Rotation +1°, P2 | 0,0259 | 0,0197–0,0325 |
| Recadrage 5 %, P2 | 0,0179 | 0,0132–0,0230 |
| Réduction-restauration ×0,8, P2 | 0,0347 | 0,0282–0,0415 |

Selon les seuils préenregistrés, R-a ne qualifie pas ce profil pour un code correcteur. Le test scellé a ensuite été exécuté comme prévu; ses résultats et une borne théorique sans signalement sont rapportés ci-dessous.

## Inventaire du test scellé

Les 400 candidats BOSSBase et 400 candidats COCO ont été reliés au manifeste source. Les SHA-256 des PNG dérivés correspondent tous au manifeste. L’audit d’identifiants et de SHA-256 a exclu 81 candidats BOSSBase et 159 COCO déjà employés dans les résultats FHAM conservés; il reste 319 et 241 candidats éligibles. Une sélection déterministe en retient 201 par corpus. Lors de cet inventaire prétest, seuls les hashes ont été calculés : le champ `pixels_opened=false` dans le manifeste décrit cet état antérieur à l’évaluation. Les pixels ont ensuite été évalués après le commit de gel.

La configuration S3/λ=0,5 et le seuil R-a 0,5 ont été fixés par LFW-val. Le commit prétest est `82dfb150ea5d73010d618be39052cd871dec2a4b`. L’évaluation scellée a ensuite été exécutée une seule fois sur 201 couvertures BOSSBase et 201 COCO. Elle comprend 4 824 messages par combinaison corpus/transformation/chemin, avec 10 000 réplications bootstrap par grappes. Les 402 couvertures ont toutes 408 lignes brutes; le fichier compressé totalise 164 016 lignes et son SHA-256 concorde avec la provenance. Le calcul a duré 4 339,4 secondes (72,3 minutes). Le manifeste, la provenance logicielle, les empreintes des scripts et les résultats bruts compressés sont conservés dans `results/stability_step1/`.

La faisabilité d’affectation est de 100 % dans les 34 cellules corpus/chemin/transformation. Cela confirme que le goulot mesuré après transformation est la reconstruction, non l’affectation initiale.

| Transformation | Chemin | BOSSBase : justesse | Sources exactes | BOSSBase : borne 1−2e | COCO : justesse | Sources exactes | COCO : borne 1−2e |
|---|---|---:|---:|---:|---:|---:|---:|
| JPEG 60 | P1 | 47,36 % | 3/4 824 | −0,053 | 55,78 % | 19/4 824 | 0,116 |
| Bruit σ=3 | P1 | 60,72 % | 75/4 824 | 0,214 | 70,12 % | 112/4 824 | 0,402 |
| Rotation −1,5° | P2 | 76,84 % | 152/4 824 | 0,537 | 80,80 % | 238/4 824 | 0,616 |
| Recadrage 10 % | P2 | 57,27 % | 10/4 824 | 0,145 | 59,64 % | 13/4 824 | 0,193 |
| Réduction ×0,7 | P2 | 62,13 % | 43/4 824 | 0,243 | 66,12 % | 49/4 824 | 0,322 |
| Rotation +1° puis JPEG 75 | P2 | 51,61 % | 8/4 824 | 0,032 | 58,63 % | 13/4 824 | 0,173 |

La borne `1−2e = 2a−1` suppose un code MDS idéal corrigeant des erreurs de symbole sans signalement et constitue un rendement théorique, pas un résultat de Reed–Solomon mesuré. Les estimations ponctuelles sont négatives pour JPEG 60/BOSSBase, sous 0,40 dans la plupart des cellules, et proches de 0,40 pour bruit σ=3/COCO (0,402). Rotation −1,5°/COCO atteint 0,616 en estimation ponctuelle, mais l’IC 95 % transformé de la justesse donne une borne inférieure de 0,597, sous le seuil vert préenregistré de 0,60. Le test conservateur ne donne donc pas encore de feu vert sans signalement; la rotation reste le cas prioritaire pour un essai séparé. Ces données ne valident pas un code correcteur.

ORB/RANSAC réussit le recalage sur 99,50 % des images BOSSBase et 100 % des images COCO pour les quatre transformations géométriques. Il améliore fortement la justesse par rapport aux coordonnées fixes, surtout en rotation et recadrage. La récupération exacte du message source reste rare : les comptes du tableau correspondent aux messages décompressés correctement parmi 4 824 essais par cellule. Au total, 735 des 57 888 messages primaires sont récupérés exactement (1,27 %).

Le rendement maximal R-a, calculé comme `R_max = 1 − f − 2s`, demeure faible. Sur les chemins primaires, les bornes supérieures des IC à 95 % varient de 1,41 % à 2,35 %; la plus basse borne inférieure est 1,14 %. **Toutes les classes de transformation sont en zone rouge selon le critère préenregistré appliqué au signalement R-a**. Ce no-go concerne le profil d’effacement R-a testé. La borne sans signalement décrit un autre profil de décodage et ne suffit pas à établir sa performance réelle.

## Vérification des hypothèses H1–H3

Les contrastes sont appariés par couverture sur LFW-val, chemin P2, λ=0,5, avec 10 000 réplications bootstrap par grappes et correction de Holm sur les deux transformations de chaque hypothèse. Une couverture sur 100 n’avait aucune affectation faisable pour S1–S3; l’analyse conditionnelle porte donc sur les 99 couvertures faisables (faisabilité moyenne : 96,25 %).

Les IC sont issus du bootstrap à 10 000 tirages. Les p-values proviennent d’un test de permutation apparié par inversion de signe à 100 000 tirages, puis de l’ajustement de Holm sur les deux transformations. Aucun tirage ne dépasse la statistique observée : la plus petite p-value Monte Carlo est `1/100001 ≈ 0,00001`, puis `p_Holm ≈ 0,00002`. Ce n’est pas une p-value bootstrap. Ces comparaisons ne portent que sur LFW-val; elles n’établissent pas le gain de S2 sur images naturelles, car le test scellé n’a évalué que S3/λ=0,5.

| Hypothèse | Transformation | Différence de justesse | IC 95 % | p de Holm | Verdict |
|---|---|---:|---:|---:|---|
| H1 : S2−S1 | Rotation +1° | +3,86 points | +2,96 à +4,81 | 0,00002 | Soutenue |
| H1 : S2−S1 | Recadrage 5 % | +3,70 points | +2,86 à +4,56 | 0,00002 | Soutenue |
| H2 : S3−S2 | Rotation +1° | −0,42 point | −0,85 à +0,00 | 0,10970 | Non soutenue |
| H2 : S3−S2 | Recadrage 5 % | −0,25 point | −0,68 à +0,18 | 0,25358 | Non soutenue |

L’élargissement des transformations de développement améliore la justesse sous rotation et recadrage sur LFW-val. Le score continu S3 n’améliore pas la justesse par rapport à S2; sa condition de gain échoue. Le score de Brier n’a donc pas été utilisé pour soutenir H2 et la calibration hors échantillon de S3 n’est pas établie. La sélection S3/λ=0,5 reste le choix de validation fixé par la règle de coût parmi les configurations à moins d’une erreur-type du meilleur résultat.

Sur le test scellé, les différences P3−P2 quantifient la perte imputable au recalage, et P0−P3 la perte entre l’image intacte et l’inverse géométrique oracle. Les valeurs sont des points de pourcentage; les IC sont bootstrapés par couverture (201 par corpus).

| Corpus | Transformation | P3−P2, coût du recalage (IC 95 %) | P0−P3, perte après transformation (IC 95 %) |
|---|---|---:|---:|
| BOSSBase | Rotation −1,5° | 7,22 (6,12–8,40) | 15,93 (15,14–16,77) |
| BOSSBase | Recadrage 10 % | 14,91 (13,67–16,19) | 27,83 (26,91–28,77) |
| BOSSBase | Réduction ×0,7 | 1,27 (0,90–1,75) | 36,60 (35,09–38,11) |
| BOSSBase | Rotation +1° puis JPEG 75 | 3,21 (2,70–3,76) | 45,18 (43,47–46,87) |
| COCO | Rotation −1,5° | 4,75 (4,09–5,51) | 14,45 (13,78–15,12) |
| COCO | Recadrage 10 % | 12,18 (11,26–13,14) | 28,18 (27,54–28,84) |
| COCO | Réduction ×0,7 | 0,78 (0,60–0,98) | 33,09 (31,88–34,27) |
| COCO | Rotation +1° puis JPEG 75 | 2,41 (2,00–2,85) | 38,96 (37,48–40,48) |

Le recalage explique une part importante de la perte pour le recadrage et une part plus modérée pour la rotation. Sous réduction, P2 est proche de l’oracle P3, mais la perte par rapport à P0 reste élevée : l’interpolation et l’instabilité des hachages constituent alors la limite dominante. Même avec l’inverse géométrique connu, aucune transformation ne retrouve la justesse de l’image intacte.

## Décision de l’étape 1

Le test scellé confirme une amélioration de la justesse par recalage et une bonne faisabilité initiale. La justesse géométrique P2 reste sous 85 % dans les deux corpus; la récupération exacte demeure très faible, en particulier après recadrage, redimensionnement et transformation composée. Il s’agit d’un **no-go, selon les seuils préenregistrés, pour le profil de correction avec signalement R-a**. Ce résultat n’établit pas que tout code correcteur est impossible : la borne idéale sans signalement appelle une évaluation distincte, particulièrement pour la rotation. La différence entre LFW-val et les corpus naturels, ainsi que l’absence de comparaison S0–S3 sur ces derniers, limitent aussi les conclusions sur la généralisation des paramètres et l’apport propre de la pondération de stabilité. Le mode catalogue reste l’usage supporté pour une récupération exacte; la robustesse après transformation demeure une limite de la méthode. Les résultats détaillés sont disponibles dans `sealed_test_summary.csv`, les lignes brutes dans `sealed_test_raw.csv.gz` et la provenance complète dans `sealed_test_provenance.json`.

L’étape 2 ne sera engagée qu’après le go de l’auteur.

## Référence du mode catalogue

Le pilote existant `results/geometry_registration_pilot.csv` rapporte 40/40 récupérations canoniques exactes pour chacune des deux transformations (rotation +1° et recadrage-restauration 5 %). Il utilise cinq messages de 40 caractères sur chacun de huit contenus contrôlés, tous présents à l’identique dans une galerie de 219 images; l’identification catalogue est 8/8 pour chaque transformation. Ce résultat étaye le mode catalogue en univers fermé, avec requêtes déjà présentes dans la galerie. Il ne mesure pas une recherche sur des images inconnues ni une généralisation hors de cette galerie.

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
- `results/stability_step1/sealed_test_summary.csv`
- `results/stability_step1/sealed_test_raw.csv.gz`
- `results/stability_step1/sealed_test_provenance.json`
- `results/stability_step1/validation_hypothesis_contrasts.csv`
- `results/stability_step1/validation_hypothesis_contrasts.json`
- `results/stability_step1/sealed_geometry_diagnostics.csv`
- `scripts/analyze_step1_hypotheses.py`
