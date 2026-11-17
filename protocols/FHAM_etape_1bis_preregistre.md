# FHAM — Protocole de l'étape 1bis : images naturelles, profils de hachage, signalement

Nov 16, 2026 · @Ekodeck Stéphane

## 1. Objectif, questions et hypothèses

L'étape 1bis rejoue l'étude de la stabilité dans le régime des images naturelles, pour décider si le hachage actuel peut devenir assez stable pour un code correcteur ou s'il faut en changer. Elle est **exploratoire** : toute conclusion confirmatoire exige un nouveau jeu scellé (phase B) et le go explicite de l'auteur avant le lancement.

**Statut du document (17 novembre 2026).** Protocole corrigé et gelé au commit 57761f8 après le go explicite de l'auteur pour l'étape 1bis. Aucun résultat 1bis n'est disponible. Avant le contrôle de régression, un amendement d'environnement est consigné : l'exécution utilisera le Python 3.11.9 et les versions indiquées dans `results/stability_step1/step1bis_environment.json`, disponibles sur le poste, plutôt que l'environnement Python 3.13 décrit par le verrou initial. Cet amendement est commité avant tout calcul. Les résultats porteront cette déviation comme limite de reproductibilité. La phase B et l'ouverture des pixels d'évaluation BOWS2-C restent soumises à un go distinct après les barrières de la section 9.

**Amendements de pré-enregistrement.** Les clauses ci-dessous remplacent toute valeur contradictoire des sections suivantes : dimensions BOWS2 256×256 (sections 3–4); exclusions historiques (section 3); audit perceptuel limité aux empreintes de déduplication et sans inspection ni métrique (section 3); longueur de mot de code et faisabilité RS (sections 4, 6–9); pont Q0 sur BOWS2-B (sections 5, 8); COCO déjà utilisé à l'étape 1 (section 10); budget recalculé après mesure du pilote (section 8). Tout résultat sur BOWS2-C demeure interdit avant le go de phase B, hormis l'empreinte perceptuelle de déduplication décrite en section 3.

**Point de départ (rapport de l'étape 1, commit a0709f9).**

| Constat | Valeur |
| --- | --- |
| Justesse par symbole, test scellé BOSSBase et COCO (6 transformations) | 47,36 % à 80,80 % |
| Justesse par symbole, LFW-val (5 transformations, chemin primaire) | 9,31 % à 37,84 % |
| Perte P0 − P3, après inverse géométrique oracle | 14,45 à 45,18 points |
| Faisabilité d'affectation | 100 % (test naturel), 95,29 % (LFW-val) |
| Symboles signalés par R-a | 97,59 % (LFW-val), 98,18 % en moyenne (test naturel) |
| R\_max avec R-a, bornes supérieures des IC | 1,41 à 2,35 % |
| Borne 1 − 2e sans signalement | de −0,053 (BOSSBase, JPEG 60) à 0,616 (COCO, rotation −1,5° ; borne inférieure 0,597) |
| Messages source exacts | 735 sur 57 888 (1,27 %) |
| Mode catalogue (pilote) | 40/40 par transformation, 8 contenus d'une galerie de 219 images, requêtes identiques aux entrées |

Les transformations de LFW-val et du test scellé n'étaient pas les mêmes. L'écart de justesse ne peut donc pas être attribué au seul corpus.

**Questions.**

- Q0 (pont) : sous des transformations identiques, quel écart descriptif de justesse observe-t-on entre LFW-val et BOWS2-B ? Ce contraste entre corpus ne sera pas interprété comme un effet causal isolé.
- Q1 : quel profil de hachage (taille de bloc) minimise la perte P0 − P3 ?
- Q2 : sur images naturelles, la pondération ou le filtrage par stabilité apporte-t-il un gain par rapport à S0 ?
- Q3 : un signalement réglé sur images naturelles rend-il le rendement utilisable ?
- Q4 : un code Reed–Solomon réel récupère-t-il des blocs exacts à R = 0,6, avec et sans signalement ?

**Hypothèses.**

- H4 : sous transformations identiques, la justesse sur BOWS2 dépasse celle de LFW-val d'au moins 20 points.
- H5 : la perte P0 − P3 décroît avec la taille de bloc, et au moins un profil atteint une justesse sous inverse oracle ≥ 0,95 pour JPEG 75 et bruit σ = 2.
- H6 : sur BOWS2, S3 ou S4q dépasse S0 d'au moins 3 points sous rotation et recadrage (intervalle strictement positif).
- H7 : avec un signalement réglé sur BOWS2, la récupération exacte de blocs à R = 0,6 atteint 0,90 pour JPEG 75 et bruit σ = 2.

**Hors périmètre.** Nouveau descripteur (Arr.4), sécurité, compression du jeton, catalogue en univers ouvert.

## 2. État des corrections de l'étape 1

Les corrections demandées après le test scellé sont faites dans le rapport révisé (commit a0709f9) ; trois points de fond restent ouverts et motivent l'étape 1bis.

| Point | État | Détail |
| --- | --- | --- |
| p-values | résolu | les IC viennent du bootstrap (10 000 tirages) ; les p viennent de 100 000 inversions de signe appariées, correction Monte Carlo 1/100001 puis Holm ≈ 0,00002. Ce ne sont pas des p bootstrap. |
| Portée du no-go | résolu | no-go pour le profil R-a préenregistré, pas pour tout code correcteur |
| Borne sans signalement 1 − 2e | résolu | ajoutée ; rotation COCO 0,616 (borne inférieure 0,597, juste sous 0,60), bruit COCO 0,402 (borne inférieure 0,363) : cas à étudier, aucune validation d'un code réel |
| Portée de H1 | résolu | soutenue sur LFW-val seulement ; le test naturel n'a comparé que S3 à λ = 0,5 |
| Catalogue | résolu | 40/40 vérifié : cinq messages de 40 caractères sur huit contenus présents à l'identique dans une galerie de 219 images, identification 8/8 ; univers fermé |
| Grille τ de S4 | **ouvert** | la grille absolue est inadaptée à l'échelle de s(p) (moyenne 0,0818) ; le filtre par quantile n'a pas été testé : S4q fait partie de 1bis |
| Effet corpus contre effet transformation | **ouvert** | transformations différentes entre LFW-val et test scellé : le pont de la phase A les rend identiques |
| Apport de la stabilité sur images naturelles | **ouvert** | pas de comparaison S0 à S3 hors LFW-val : question Q2 |

Le jeu scellé de l'étape 1 (201 BOSSBase + 201 COCO) est consommé : aucun réglage, aucune sélection ni aucun nouveau test ne l'utilise. Les fichiers antérieurement utilisés sont également exclus de BOWS2-A/B/C.

## 3. Données

BOWS2 est partagé en trois jeux disjoints, dont un reste scellé jusqu'à la phase B ; LFW-val ne sert qu'au pont et au contrôle de régression.

| Jeu | Taille | Rôle | Statut |
| --- | --- | --- | --- |
| BOWS2-A (développement) | 200 images | estimation de la stabilité, réglage du signalement, exploration | libre |
| BOWS2-B (validation) | 200 images | sélection de la configuration, mesure de Q0 à Q4 | libre |
| BOWS2-C (scellé) | N images, N ≥ 200 | évaluation confirmatoire (phase B) | pixels jamais ouverts avant la phase B |
| LFW-val (pont) | 100 images existantes | pont de la question Q0 et contrôle de régression du code | déjà utilisé ; jamais un test |

BOWS2 comporte 10 000 images 256 × 256 en niveaux de gris selon le manifeste du dépôt. N est fixé après le pilote de la section 7. Les 2 046 identifiants BOWS2 déjà utilisés dans les résultats historiques sont exclus : 1 998 dans la robustesse stratifiée et 60 dans le smoke test, dont 12 communs. Le pool initial maximal est donc de 7 954 images avant l'audit de doublons avec les autres corpus.

**Règles.**

- Images BOWS2 natives 256 × 256, sans redimensionnement. LFW-val reste le pont historique traité selon son prétraitement original; le contraste corpus est descriptif, pas causal.
- Partition déterministe : tri par SHA-256 du contenu, puis découpe A, B, C ; manifeste avec SHA-256 de chaque image.
- Audit avant partition : comparer SHA-256 exact et pHash 64 bits à distance ≤4 aux images déjà utilisées (LFW, 8 contrôlées, 219 stress, Scènes-11, 402 images scellées de l'étape 1, 240 candidats déjà employés et 2 046 identifiants BOWS2 historiques), et entre candidates BOWS2. Une procédure de curation dédiée peut décoder les fichiers uniquement pour calculer le pHash; elle ne produit ni aperçu, transformation, métrique, codebook ni résultat pour C. Elle écrit uniquement identifiant, SHA-256, pHash et indicateur d'exclusion. Cette opération de déduplication est préenregistrée et n'est pas une ouverture analytique de C.
- Le manifeste C porte `dedup_hash_only=true` et `evaluation_pixels_opened=false`. Après le gel, aucune transformation ni évaluation C n'est exécutée avant le go de phase B.

## 4. Facteurs expérimentaux

Quatre facteurs varient ; B = 2, le solveur global (SciPy) et les familles de messages restent ceux de l'étape 1.

**F1 : profil de hachage (taille de bloc L).** Chaque bloc est divisé en grille 3 × 3 de sous-blocs de côté L/3 et produit 4 emplacements (§4.1). Un jeton de position coûte ⌈log₂ N⌉ bits, et le théorème 1 impose n ≤ N.

| Profil | Blocs complets sur 256×256 | Emplacements N | Bits par jeton | Sous-bloc |
| --- | --- | --- | --- | --- |
| 12 × 12 | 21 × 21 | 1 764 | 11 | 4 × 4 |
| 24 × 24 | 10 × 10 | 400 | 9 | 8 × 8 |
| 36 × 36 | 7 × 7 | 196 | 8 | 12 × 12 |
| 48 × 48 | 5 × 5 | 100 | 7 | 16 × 16 |

Longueurs testées : 50, 100, 200 symboles après zlib, et 255 symboles non compressés pour un mot RS(255,k). La faisabilité est rapportée à chaque longueur et profil. Un profil dont N < n est déclaré structurellement infaisable à n; une longueur ne sert pas de critère d'élimination pour des longueurs plus courtes.

**F2 : méthode de stabilité.** Les méthodes S0 à S3 sont définies comme à l'étape 1 (dev étendu pour S2 et S3). Nouveauté : S4q, qui ne garde que les q % d'emplacements de meilleur s(p), puis applique la L1 globale sans terme de stabilité.

- S0 (λ = 1), S1, S2, S3 avec λ ∈ {0,25 ; 0,5 ; 0,75 ; 0,9}.
- S4q avec q ∈ {50 % ; 30 % ; 10 %}. La faisabilité par q est rapportée.

**F3 : signalement récepteur.** Le récepteur recalcule le hachage sur K perturbations de l'image reçue (décalages d'un pixel, bruit σ = 1) et marque un symbole peu fiable si au moins m perturbations changent le hachage, ou si min z\_i < z\_flag.

- Grille : z\_flag ∈ {0,25 ; 0,5 ; 1 ; 1,5 ; 2 ; 3}, m ∈ {1 ; 2 ; 4}, K ∈ {8 ; 16}.
- Trois régimes comparés : sans signalement ; signalement réglé sur BOWS2-A ; signalement oracle (borne de référence, non réalisable).

**F4 : code.** Reed–Solomon sur GF(256), mot de code de 255 symboles, k ∈ {204 ; 153 ; 102} (R = 0,8 ; 0,6 ; 0,4), décodeur d'erreurs et d'effacements. L'affectation de 255 symboles est structurellement impossible pour L=36 et L=48 (N<255), et peut l'être pour S4q lorsque le filtre conserve moins de 255 positions. Ces cellules sont rapportées comme non faisables par capacité et q(R)=0 dans l'analyse de bout en bout; elles ne sont pas omises du dénominateur. L'analyse d'efficacité du code RS réel se limite aux cellules où n=255 est faisable.

## 5. Transformations

Le développement et la validation reprennent ceux de l'étape 1 ; le jeu scellé de 1bis utilise des paramètres jamais employés, ni au développement, ni en validation, ni au test scellé de l'étape 1.

| Famille | Développement (estimer la stabilité) | Validation (explorer, choisir) | Scellé 1bis (phase B) |
| --- | --- | --- | --- |
| JPEG | qualité 90 et 85 | qualité 75 | qualité 65 |
| Bruit gaussien | σ = 1 et 1,5 | σ = 2 | σ = 2,5 |
| Rotation | −0,5°, +0,5°, +2° | +1° | −1,25° |
| Recadrage-restauration | 3 % et 7 % | 5 % | 9 % |
| Réduction-restauration | ×0,9 | ×0,8 | ×0,75 |
| Composition | aucune | aucune | rotation −1,25° puis JPEG 65 |
| Interpolation | bilinéaire | bicubique | bicubique |

Pour le pont Q0, LFW-val et BOWS2-B sont évalués sous **les mêmes** transformations de validation.

**Chaînes de décodage.** P0 (image identique), P1 (coordonnées fixes), P2 (ORB/RANSAC avec les paramètres de l'étape 1 ; un recalage en échec compte comme un échec), P3 (inverse oracle). Chemin primaire : P1 pour JPEG et bruit, P2 pour les transformations géométriques ; P1 et P3 sont toujours rapportés.

Bibliothèques et versions figées et enregistrées ; graines distinctes pour le bruit, RANSAC et la perturbation du récepteur ; un sous-ensemble est rejoué avec une seconde implémentation JPEG et d'interpolation.

## 6. Métriques et simulation Reed–Solomon

La phase A est jugée sur la justesse sous inverse oracle (qualité du hachage seul), puis sur la récupération réelle de blocs Reed–Solomon (la décision qui compte pour l'étape 2).

| Métrique | Définition | Sert à |
| --- | --- | --- |
| a\_P3 | fraction d'octets exacts sous inverse oracle, cas faisables | Q1, barrière G-A1 |
| a\_P2, a\_P1 | idem pour recalage ORB/RANSAC et coordonnées fixes | réalisme |
| Δ\_corpus | a(BOWS2-B) − a(LFW-val), mêmes transformations et configuration | Q0, H4 |
| Faisabilité par longueur | taux de cas faisables à 50, 100, 200 symboles, par profil et par q | capacité |
| Bits par jeton, D₁ | ⌈log₂ N⌉ ; D₁ moyen et max δ moyen | coût |
| f, s, rappel, précision | fraction signalée, erreurs silencieuses, erreurs signalées / erreurs, erreurs signalées / symboles signalés | Q3 |
| R\_max | 1 − f − 2s dans les trois régimes de signalement ; sans signalement, 1 − 2e | borne de comparaison |
| q(R) | fraction de blocs Reed–Solomon récupérés exactement | Q4, H7, barrière G-A3 |
| Bits retournés | histogramme du poids de Hamming de h' XOR h et du rang des bits | diagnostic |
| Calibration | courbe de fiabilité, score de Brier, Spearman pour S3 | Q2 |

**Simulation Reed–Solomon sur blocs réels.** Un bloc est un mot de code RS(255, k) calculé sur k octets aléatoires ; ses 255 symboles passent dans FHAM comme un message ordinaire (zlib désactivé, un mot de code étant déjà quasi uniforme), subissent la transformation, sont décodés sur le chemin primaire, puis décodés par RS avec les effacements du régime de signalement considéré. q(R) est la fraction de blocs dont les k octets sont récupérés sans erreur. Cette mesure remplace la borne théorique : elle inclut les erreurs corrélées et la perte du décodeur réel.

```latex
R_{\max} \le 1 - f - 2s, \qquad R_{\max}^{\text{sans signalement}} \le 1 - 2e = 2a - 1
```

Le multiplicateur de taille du record est 1 / R.

## 7. Statistiques et taille d'échantillon

L'unité statistique est la couverture, car les messages et les blocs d'une même couverture partagent ses emplacements. Les méthodes sont celles du rapport révisé de l'étape 1, pour que les résultats restent comparables.

- **Intervalles.** Bootstrap par grappes sur les couvertures, 10 000 tirages, intervalle à 95 % par percentiles. Intervalles de Wilson pour les taux de faisabilité.
- **Tests.** Test de permutation apparié par inversion de signe, 100 000 tirages, p = (1 + k) / (100 001) où k est le nombre de tirages au moins aussi extrêmes ; plus petit p atteignable ≈ 0,00001. Correction de Holm sur chaque famille d'hypothèses (H4 à H7). Les IC restent la preuve principale ; les p ne sont jamais présentés comme des p bootstrap.
- **Comparaisons appariées.** Mêmes (couverture, message, transformation) pour toutes les configurations ; pour le pont Q0, mêmes transformations et même configuration sur LFW-val et BOWS2-B.
- **Taille du jeu scellé.** Un pilote de 20 couvertures de BOWS2-A estime sd\_Δ pour les contrastes de justesse et sd\_q pour le taux de succès RS, à partir de la fraction de blocs réussis par couverture. N est fixé pour une demi-largeur d'intervalle de 3 points sur les deux critères, avec un plancher de 200 :

```latex
N = \max\left(200,\ \left\lceil \left( \frac{1{,}96 \cdot sd_{\Delta}}{0{,}03} \right)^{2} \right\rceil,\ \left\lceil \left( \frac{1{,}96 \cdot sd_{q}}{0{,}03} \right)^{2} \right\rceil \right)
```

Les couvertures, et non les blocs individuels, sont les grappes du calcul de sd\_q. Le code RS, le profil, le régime de signalement et les attaques utilisés pour le pilote de dimensionnement sont gelés dans le protocole avant son exécution.

- **Blocs Reed–Solomon.** 5 blocs par couverture et par valeur de k ; q(R) avec IC par grappes sur les couvertures.
- **Exploratoire contre confirmatoire.** Les résultats de la phase A (BOWS2-A et B) sont explorés sur une grille large : toutes les cellules sont rapportées, aucune n'est présentée comme confirmation. La configuration retenue est réévaluée sur BOWS2-C pour limiter la malédiction du gagnant.
- **Graines.** Une graine par source d'aléa : partition, messages, blocs RS, bruit, RANSAC, perturbations du récepteur.

## 8. Procédure par phases et budget

La phase A (exploratoire) occupe les étapes 4 à 8 ; la phase B (confirmatoire, jeu scellé) n'ouvre que si les barrières de la section 9 sont franchies. Les points d'arrêt sont les étapes 1, 2 et 8.

1. **Go et gel (arrêt).** Go explicite de l'auteur. Gel et commit de ce document, de la branche, des versions exactes (consignées dans le fichier de provenance), des graines, du manifeste BOWS2 et de l'audit de doublons. L'environnement réellement disponible est utilisé sans mise à niveau de dépendance durant l'expérience. BOWS2-C : pixels non ouverts.
2. **Contrôle de régression (arrêt).** Sur 20 couvertures de LFW-val, reproduire la configuration S3, λ = 0,5, profil 12 × 12 du rapport de l'étape 1 ; écart toleré ≤ 0,05 point (l'écart maximal de la reproduction précédente était de 0,048).
3. **Instrumenter.** Paramètre de taille de bloc ; filtre S4q ; signalement par vote ; harnais Reed–Solomon (encodage, insertion comme message, décodage avec effacements) ; stockage des différences d\_i.
4. **Pilote.** 20 couvertures de BOWS2-A pour estimer sd\_Δ et fixer N (section 7).
5. **Étape A : profils et pont.** 100 couvertures de BOWS2-A × 8 messages (4 familles × 2 longueurs × 1 message), 4 profils × {S0, S3 λ = 0,5}, transformations de validation, chaînes P0 à P3. Pont Q0 : même protocole sur 100 couvertures de BOWS2-B et les 100 couvertures LFW-val, profil 12 × 12, S0 et S3, mêmes attaques et mêmes messages. Barrière G-A1.
6. **Étape B : stabilité.** Sur le ou les deux meilleurs profils, grille F2 sur BOWS2-A (100 couvertures × 8 messages) ; les 3 meilleures configurations selon la règle de la section 9 sont réévaluées sur BOWS2-B (200 couvertures × 24 messages). Barrière G-A2.
7. **Étape C : signalement.** Grille F3 réglée sur BOWS2-A, évaluée sur BOWS2-B dans les trois régimes.
8. **Étape D : Reed–Solomon (arrêt).** Blocs RS sur BOWS2-B : 200 couvertures × 5 blocs × 3 valeurs de k. Barrière G-A3, puis rapport exploratoire et décision d'ouvrir ou non la phase B.
9. **Phase B.** Gel de la configuration (commit), ouverture de BOWS2-C une seule fois, transformations du jeu scellé, k = 153 (R = 0,6) pour les blocs ; aucun réglage après ouverture.
10. **Rapport et décision.** Tableaux, figures, feux de la section 9, écart à ce protocole.

**Budget de calcul.** Les durées de l'étape 1 ne sont pas extrapolées : elles proviennent d'images 512 × 512 et d'un profil différent. Avant la grille, le pilote chronomètre séparément le décodage, l'extraction des descripteurs, l'affectation, chaque attaque et le décodage RS sur les dimensions natives 256 × 256. Le journal consigne matériel, versions, nombre de couvertures, de configurations et de lignes, ainsi que temps mur et mémoire maximale. Le plan de calcul final est dérivé de ces mesures et de la grille effectivement définie ci-dessus; aucune durée prévisionnelle non mesurée n'est présentée comme résultat.

## 9. Barrières et feux de décision

La phase A franchit trois barrières avant l'ouverture du jeu scellé ; les seuils sont fixés avant toute exécution, modifiables avant le gel de la section 8, jamais après. Les classes sont jugées séparément : photométrique (JPEG, bruit, chemin P1) et géométrique (rotation, recadrage, réduction, chemin P2).

**Règle de choix de la configuration (comme à l'étape 1).** Parmi les configurations dont la faisabilité est ≥ 95 % à 100 symboles (B = 2) et dont le D₁ moyen est ≤ 5 fois celui de S0, retenir la plus haute justesse a ; si plusieurs sont à moins d'une erreur-type de la meilleure, retenir la moins coûteuse (D₁ le plus bas).

| Barrière | Condition (phase A, BOWS2-B) | Si franchie | Sinon |
| --- | --- | --- | --- |
| G-A1, hachage | au moins un profil avec a\_P3 ≥ 0,95 sous JPEG 75 et bruit σ = 2 (borne inférieure de l'IC ≥ 0,92) et faisabilité ≥ 95 % à 100 symboles | passer à G-A2 | orange si le meilleur a\_P3 est dans \[0,90 ; 0,95\[ : combiner profil, S4q et signalement, puis réévaluer ; rouge si < 0,90 : arrêt de 1bis, étape 1ter (hachage à marge ou autre descripteur) |
| G-A2, stabilité utile | Δa (meilleure méthode pondérée ou filtrée − S0) strictement positif, IC 95 %, sous rotation et recadrage, au profil retenu | garder la stabilité | utiliser S0 : plus simple, D₁ minimal |
| G-A3, code | borne inférieure de l'IC de q(R = 0,6) ≥ 0,90 dans au moins un régime de signalement | ouvrir la phase B pour cette classe | orange si 0,50 ≤ q < 0,90 : itérer sur le signalement ou le profil ; rouge si q < 0,50 : pas de phase B pour cette classe |

Q0 et H4 sont informatives : aucune barrière n'en dépend. Le cas de la rotation sans signalement (borne 0,597 pour COCO à l'étape 1) est jugé par G-A3 avec le chemin P2 et le régime sans signalement.

**Feux de la phase B (jeu scellé BOWS2-C, borne inférieure de l'IC de q(R = 0,6)).**

| Feu | Condition | Suite |
| --- | --- | --- |
| Vert | q ≥ 0,90 | go pour l'étape 2 pour cette classe |
| Orange | 0,50 ≤ q < 0,90 | itération, avec un nouveau jeu scellé |
| Rouge | q < 0,50 | mode catalogue ; robustesse documentée comme limite |

**Coût et compromis.** À R = 0,6, le mot RS contient 255 symboles pour 153 octets utiles, soit un facteur d'expansion de 255/153 ≈ 1,67 avant métadonnées. Sur BOWS2 natif 256 × 256, les jetons occupent respectivement 11, 9, 8 et 7 bits pour L = 12, 24, 36 et 48. Avec le résidu actuel de 3 bits, le coût brut par symbole est 14, 12, 11 et 10 bits (hors en-têtes et chiffrement), soit une baisse de 12,5 %, 25 %, 31,25 % et 37,5 % par rapport aux 16 bits de L = 12. Ces réductions s'accompagnent d'une capacité maximale de 1 764, 400, 196 et 100 positions; seuls les deux premiers profils peuvent porter un mot de 255 symboles sans raccourcissement.

**Verdict sur les hypothèses.** H4 : Δ\_corpus ≥ 20 points avec un IC strictement au-dessus de 20. H5 : G-A1 franchie et perte P0 − P3 décroissante avec L. H6 : Δa ≥ 3 points avec un IC strictement positif. H7 : G-A3 franchie.

## 10. Menaces à la validité et plans de repli

Les deux risques principaux sont de prendre un résultat exploratoire pour une confirmation et de conclure sur un régime d'images qui ne représente pas l'usage visé.

| Menace | Effet possible | Parade |
| --- | --- | --- |
| Exploration large puis sélection (malédiction du gagnant) | justesse surestimée | toutes les cellules rapportées ; réévaluation de la configuration retenue sur BOWS2-B puis BOWS2-C |
| Contamination du jeu scellé | confirmation invalide | pixels de BOWS2-C jamais ouverts avant la phase B ; manifeste et commit de gel ; un seul passage |
| Quasi-doublons entre BOWS2 et les jeux déjà utilisés | fuite | audit par empreinte perceptuelle (Hamming ≤ 4) et exclusion |
| BOWS2 non représentatif de l'usage | conclusion trop locale | contrôle sur un échantillon COCO disjoint des 201 images utilisées à l'étape 1 et audit de doublons ; il s'agit d'un échantillon nouveau du corpus COCO, pas d'un corpus jusque-là inutilisé ; limites écrites |
| Effet corpus mélangé à l'effet transformation | mauvaise attribution | pont Q0 avec transformations identiques |
| Profil à faible capacité (36 × 36, 48 × 48) | faisabilité insuffisante | faisabilité rapportée par longueur ; écart à moins de 95 % à 100 symboles |
| Erreurs corrélées dans un bloc RS | rendement réel plus bas que la borne | q(R) mesuré sur blocs réels, pas déduit d'une loi |
| Un seul angle de rotation et un seul rapport de recadrage par jeu | généralisation limitée | paramètres distincts par jeu ; limite écrite |
| Bibliothèque JPEG ou d'interpolation | résultats liés à un outil | seconde implémentation sur un sous-ensemble |
| Comparaisons multiples | faux positifs | Holm par famille d'hypothèses ; IC comme preuve principale |

**Plans de repli.**

| Constat | Action |
| --- | --- |
| G-A1 rouge (aucun profil ≥ 0,90) | arrêt de 1bis ; étape 1ter : hachage à marge minimale ou hystérésis, ou autre descripteur (Arr.4 après mesure de sa stabilité) |
| G-A1 orange | combiner meilleur profil, S4q et signalement par vote ; réévaluer sur BOWS2-B |
| G-A2 non franchie | abandonner la pondération de stabilité ; S0 comme méthode par défaut |
| G-A3 rouge malgré G-A1 verte | l'erreur n'est pas assez rare ou pas assez bien signalée : tester le signalement par vote et les valeurs de k plus basses ; sinon mode catalogue |
| Tout rouge | acter la limite : mode catalogue comme usage supporté, robustesse documentée |

## 11. Livrables et schéma des données

L'étape produit un dépôt reproductible, des données brutes, sept tableaux, quatre figures et une page de décision ; tout écart à ce protocole y est listé.

**Données brutes.** Un enregistrement par (couverture, message ou bloc, configuration, transformation, chaîne), avec l'en-tête suivant :

```csv
cover_id,corpus,split,block_size,n_locations,token_bits,B,family,length,msg_seed,method,lambda,filter_q,flag_z,flag_vote,flag_K,transform,transform_params,interp,path,feasible,D1,max_abs_delta,n_symbols,n_correct,n_flagged,n_flagged_wrong,n_silent_err,flipped_bits_hist,rs_k,rs_block_ok,solve_ms
```

**Tableaux.**

| Tableau | Contenu |
| --- | --- |
| T1 | contrôle de régression : valeurs obtenues, valeurs du rapport de l'étape 1, écart |
| T2 | pont Q0 : a sur LFW-val et BOWS2-B, mêmes transformations, Δ\_corpus avec IC |
| T3 | profils : faisabilité par longueur, bits par jeton, a\_P3, a\_P2, a\_P1, perte P0 − P3 |
| T4 | stabilité : S0 à S4q, a, Δa par rapport à S0, D₁, faisabilité, calibration |
| T5 | signalement : f, s, rappel, précision, R\_max dans les trois régimes |
| T6 | Reed–Solomon : q(R) par k, par transformation et par régime, avec IC |
| T7 | phase B : configuration figée, q(R = 0,6), feu de décision, par classe |

**Figures.** Histogramme des bits retournés ; a\_P3 en fonction de la taille de bloc ; courbe de fiabilité ; q(R) en fonction de R.

**Page de décision.** Une page : feu par classe de transformation, hypothèses H4 à H7 soutenues ou non, écarts à ce protocole, et suite recommandée (étape 2, étape 1ter ou mode catalogue).
