# FHAM — Protocole de l'étape 1ter : plafond de la sélection et descripteur

18 novembre 2026 · @Ekodeck Stéphane

**Amendement pré-expérience (18 novembre 2026).** Les incohérences relevées avant lancement sont corrigées ci-dessous, sans ouvrir les pixels des jeux D, E, C ou F. Le GO explicite de l’auteur a été reçu le 18 novembre 2026. Les mesures commencent après le commit de gel de cet amendement. BOWS2-C et BOSSBase-F restent fermés jusqu’à l’étape 6.

## 1. Objectif, point de départ et questions

L'étape 1ter décide si le hachage actuel peut atteindre une justesse de 0,95 sous JPEG 75 et bruit σ = 2 par sélection d'emplacements robustes, ou si le descripteur doit changer. Elle est **exploratoire** ; toute conclusion confirmatoire passe par la phase C, sur des images jamais évaluées.

**Point de départ (rapport 1bis, profil 12 × 12, B = 2, BOWS2-B, inverse oracle P3).**

| Constat | Valeur |
| --- | --- |
| S0 : JPEG 75 / bruit σ = 2 | 22,64 % / 31,24 % |
| S2, λ = 0,50 : JPEG 75 / bruit σ = 2 | 56,42 % / 69,66 % (D₁ = 2,33 fois S0) |
| S2, λ = 0,75 et λ = 0,90 | moyennes arrondies identiques : 54,61 % / 67,79 % ; D₁ égal à S0 pour chacun des 4 800 messages ; récupération exacte identique, avec de faibles écarts de justesse partielle sur 496/67 200 lignes |
| S2, λ = 0,25 : justesse moyenne P3 sur 5 transformations | 76,81 % (D₁ = 15,41 fois S0), écartée par la règle de coût |
| S4q | aucune configuration admissible |
| Récepteur réel, S2 λ = 0,50 | rotation P2 75,63 %, recadrage P2 52,69 % |
| Messages exacts | 0,23 % (JPEG), 1,81 % (bruit), 2,71 % (rotation P2), 0,10 % (recadrage P2) |
| Barrière G-A1 | rouge |

Le hachage est formé de 8 bits, chacun issu d'une comparaison entre scores spectraux de sous-blocs (§4.1) ; un bit qui bascule change le hachage de ±2^k.

**Questions.**

- Q1 (plafond) : sous la sévérité cible, combien d'emplacements robustes une couverture offre-t-elle, et suffisent-ils à affecter un message de 100 et de 200 octets ?
- Q2 (sévérité) : estimer la stabilité sur des perturbations dont la sévérité encadre la cible améliore-t-il la justesse ?
- Q3 (objectif) : un coût fondé sur la probabilité d'exactitude, avec une contrainte explicite sur D₁ et B ∈ {2 ; 4 ; 8}, repousse-t-il la frontière justesse × bits par symbole ?
- Q4 (diagnostic) : quelles comparaisons du hachage basculent, et à quelle marge ?
- Q5 (profils) : le classement observé avec S3 tient-il pour L=12 et L=24 sur BOWS2 natif 256×256 ?
- Q6 (descripteur) : si la sélection plafonne, quel descripteur candidat atteint le seuil ?

**Hypothèses.**

- H8 : sur au moins 90 % des couvertures, une affectation faisable à B≤8 existe avec les seuls emplacements robustes pour les 12 messages de 100 octets source (4 familles × 3 indices), après zlib-9.
- H9 : le coût logarithmique avec stabilité estimée sur sévérité encadrante atteint a\_P3 ≥ 0,95 sous JPEG 75 et bruit σ = 2.
- H10 : si H8 est fausse, au moins un descripteur candidat a une fraction d'emplacements robustes au moins double de celle du descripteur spectral actuel.

**Hors périmètre.** Code correcteur, signalement, catalogue, sécurité. La géométrie (P2, P3) est mesurée en secondaire.

## 2. Préalables à vérifier

Cinq vérifications sur 1bis précèdent toute nouvelle expérience, parce que leur résultat peut changer la lecture de la barrière G-A1.

| Vérification | Pourquoi | Critère |
| --- | --- | --- |
| V1, profils | le rapport F2 présente L=12 seul | le dépistage archivé a comparé 12/24/36/48 avec S0 et S3, λ=0,5 ; seul L=12 satisfait l’admissibilité. Il s’agit de S3, pas de S2 empirique |
| V2, départage | vérifier normalisation et D₁ | le code divise bien |δ| par B=2 ; λ=0,75 et 0,90 ont D₁ égal à S0 pour chacun des 4 800 messages B |
| V3, doublons | deux configurations S2 proches | les taux de messages exacts sont identiques entre λ=0,75 et 0,90 ; 496/67 200 justesses partielles diffèrent, écart maximal 1,14 point. Équivalentes en D₁ et récupération exacte, elles ne sont pas identiques ligne par ligne |
| V4, sorties brutes | histogramme des bits et pont Q0 absents du rapport narratif | Q0 existe : 100 couvertures BOWS2-B et 100 LFW-val. Les XOR/marges bit-à-bit ne sont pas stockés ; les mesurer sur D à l’étape 2 |
| V5, écarts en P2 | G-A2 n’est donnée qu’en P3 | sur B (200 couvertures), S2 λ=0,50 − S0 en P2 : rotation +34,57 points [33,30; 35,85], recadrage +31,42 [30,37; 32,48] |

**Interprétation de V2.** Le code utilise c=λ|δ|/B+(1−λ)(1−s), B=2. Pour un échange local d’un cran, le coût résiduel vaut λ/B et le gain de stabilité est au plus 1−λ ; égalité à λ=B/(B+1)=2/3. C’est une heuristique, pas un résultat global : les échanges d’affectation peuvent concerner plusieurs symboles.

**Budget.** Mon estimation de calcul de 1bis était environ dix fois trop haute (A en 491 s, B en 819 s). Le budget de la section 8 s'appuie donc sur le temps mesuré de construction d'un codebook (428 ms, profil 12 × 12) et sur les durées réelles de 1bis.

## 3. Données

Deux nouveaux jeux de BOWS2 servent au développement et à la validation ; BOWS2-C reste scellé, et un corpus frais de BOSSBase s'y ajoute pour la phase C.

| Jeu | Taille | Rôle | Statut |
| --- | --- | --- | --- |
| BOWS2-D (développement) | 200 images | tirages, diagnostics et criblage ; étapes 2–3 sur les 100 premières | libre |
| BOWS2-E (validation) | 200 images | choix et mesures de validation | libre |
| BOWS2-C | 7 125 images réservées (N≥200 requis) | phase C | jamais ouvert pour une mesure |
| BOSSBase-F | 200 images | généralisation en phase C | tirées hors des 400 candidats de l’étape 1 |

BOWS2-A et BOWS2-B sont déjà exploités en 1bis et ne servent plus que de contrôle de régression.

**Règles.**

- Jeux disjoints entre eux et de tous les jeux déjà consommés (LFW, 8 contrôlées, 219 stress, Scènes-11, 402 images scellées de l'étape 1, BOWS2-A, B et C).
- Résolutions natives, sans redimensionnement : BOWS2-D/E/C = 256×256 ; BOSSBase-F = 512×512. Les comparaisons entre corpus sont rapportées par corpus et avec leur capacité de codebook propre.
- Partition déterministe par SHA-256 du contenu ; manifeste avec le SHA-256 de chaque image.
- Audit de doublons : exclure toute image dont l'empreinte perceptuelle (64 bits) est à distance de Hamming ≤ 4 d'une image déjà utilisée, et les doublons entre jeux.
- Le manifeste BOWS2-C gelé en 1bis contenait 7 525 images admissibles. Avant toute ouverture des pixels, un amendement hash-only réaffecte 200 images à D, 200 à E et réserve les 7 125 autres à C. Pour ces seules 7 525 lignes, trier par `SHA256("FHAM-1ter-20261118:" || source_sha256)` en ordre hexadécimal croissant, départager par `source_id` ; les rangs 1–200 forment D, 201–400 E, le reste C. A/B restent inchangés. Les manifestes révisés D/E/C sont commités avant les métriques. Ce changement de partition est déclaré, sans consultation analytique des pixels.
- BOSSBase-F est tiré de la source locale de 10 000 PGM 512×512. Exclure tous les 400 candidats du manifeste scellé de l’étape 1, les identifiants/hashes évalués et les quasi-doublons pHash ≤4 ; trier les éligibles par `SHA256("FHAM-1ter-20261118:" || source_sha256)` puis `source_id`, et retenir les 200 premiers. Son manifeste porte `evaluation_pixels_opened=false` jusqu’à l’étape 6.
- Les empreintes SHA/pHash sont des opérations d’inventaire ; elles ne constituent pas une évaluation FHAM. C et F restent analytiquement fermés jusqu’à l’étape 6.
- L'inventaire local BOSSBase contient 10 000 PGM ; le manifeste de candidats scellés de l'étape 1 contient 400 références BOSSBase qui sont toutes exclues de F.

## 4. Facteurs

Cinq familles de facteurs ; les étapes de la section 8 les activent selon l'embranchement décidé par le plafond de la sélection. Le profil reste 12 × 12 sauf décision de G-T0.

**F1 : estimation de la stabilité.** Calculer séparément ŝ_JPEG(p) et ŝ_bruit(p) à partir de K=100 tirages photométriques par famille, avec le lissage suivant :

```latex
\hat{s}_f(p) = \frac{K - f_f(p) + 1}{K + 2}
```

où f_f(p) est le nombre de basculements dans la famille f. L’estimateur primaire est E-encadrant ; E-origine (les dix transformations de 1bis) est un comparateur descriptif et n’est jamais mélangé à E-encadrant. Pour C1/C2, le score conservateur est ŝ_min(p)=min(ŝ_JPEG(p),ŝ_bruit(p)); rapporter/calibrer les familles séparément. Un emplacement est **robuste** si aucun basculement n’est observé dans les 100 tirages JPEG et dans les 100 tirages bruit. La borne Clopper–Pearson 2,95 % à 95 % vaut séparément par famille ; aucune garantie simultanée n’en est déduite.

**F2 : coût de l'affectation.** D₁ désigne la somme entière par message, D₁=Σ|δⱼ| ; les tableaux donnent aussi la moyenne par symbole D₁/n.

| Coût | Définition | Rôle |
| --- | --- | --- |
| C0, référence résiduelle | minimiser D₁=Σⱼ|δⱼ| sous |δⱼ|≤B | référence sans terme de stabilité |
| C1, lexicographique | minimiser D₁, puis maximiser Σ log ŝ_min parmi les affectations de D₁ minimal | départage pur |
| C2, logarithmique sous contrainte | balayage du coût −log ŝ_min(σ(j))+μ|δⱼ| ; parmi les solutions distinctes satisfaisant D₁ ≤ (1+ε)·D₁\*, retenir la meilleure stabilité observée ; ε ∈ {0 ; 0,5 ; 1 ; 2 ; 4} | frontière empirique justesse × déplacement |
| C3, filtre dur | restreindre aux emplacements robustes, puis C2 avec ε illimité | plafond de la sélection |

C1 est résolu lexicographiquement : obtenir D₁* puis maximiser Σlog ŝ_min sous D₁=D₁*. C2 est évalué par balayage du coût −log ŝ_min+μ|δ| ; conserver toutes les solutions distinctes et retenir, pour chaque ε, la meilleure stabilité parmi celles qui satisfont la borne. Ce balayage échantillonne les points soutenus de la frontière de Pareto ; il n’est pas présenté comme l’optimum exact du problème sous contrainte. Si aucune solution du balayage ne respecte une borne, la cellule est déclarée non atteinte. Σlog ŝ_min est un score de sélection conservateur, pas une probabilité conjointe démontrée ; calibrer les deux familles séparément.

**F3 : borne B∈{2;4;8}.** Le coût théorique d’information du résidu est au plus log₂(2B+1) bits (2,32; 3,17; 4,09). La largeur sérialisée fixe est ceil(log₂(2B+1)) (3; 4; 5 bits) ; rapporter ces deux coûts distinctement.

**F4 : profil et capacité.** Le descripteur actuel fournit quatre arrangements par bloc. Pour une image W×H, M=4·(⌊(W−L)/L⌋+1)·(⌊(H−L)/L⌋+1). BOWS2 natif 256×256 : L=12 → 1 764 positions (11 bits de jeton), L=24 → 400 (9 bits), L=36 →196 (8 bits), L=48 →100 (7 bits). BOSSBase 512×512 : L=12 →7 056 (13 bits), L=24 →1 764 (11 bits), L=36 →784 (10 bits), L=48 →400 (9 bits). V1 étant résolu, L=12 est primaire et L=24 secondaire ; 36/48 ne sont ajoutés que si une analyse de capacité le justifie.

**F5 : descripteurs candidats (étape 4b seulement).** Les candidats de cette campagne produisent tous quatre arrangements de hachage sur 8 bits par emplacement ; le solveur et le décodeur restent inchangés.

| Candidat | Définition |
| --- | --- |
| C-spectral | descripteur actuel (plus grande valeur propre du Gram centré), référence |
| C-moyenne | mêmes 8 comparaisons du §4.1, entre moyennes d'intensité de sous-blocs |
| C-DCT | pour chaque sous-bloc 4×4 (L=12), DCT-II orthonormale ; score scalaire `|C(0,0)|+|C(0,1)|+|C(1,0)|`; comparer les neuf scores dans les quatre ordres de §4.1 et conserver les 8 bits par arrangement |
| C-Arr4 | codebook Arr.4 d'Abdulsattar (blocs 18 × 18, neuf sous-blocs 6 × 6), réimplémenté |
| C-demi | retiré de cette campagne : le passage à deux demi-octets change l’alphabet, le codebook et le coût de jeton ; il requerra un protocole distinct après sélection d’un descripteur 8 bits |

## 5. Perturbations

Les perturbations de développement sont tirées au hasard dans des plages qui encadrent la validation, avec un trou autour des valeurs de validation et du jeu scellé ; validation et jeu scellé reprennent les paramètres de 1bis.

| Famille | Développement (tirages) | Validation (1bis) | Scellé (1bis, phase C) |
| --- | --- | --- | --- |
| JPEG | qualité \~ U\[70 ; 90\], hors \[74 ; 76\] | qualité 75 | qualité 65 |
| Bruit gaussien | σ \~ U\[1 ; 2,4\], hors \[1,9 ; 2,1\] | σ = 2 | σ = 2,5 |
| Rotation | \~ U\[−2° ; +2°\], hors \[0,9° ; 1,1°\] et \[−1,4° ; −1,1°\] | +1° | −1,25° |
| Recadrage-restauration | \~ U\[2 % ; 8 %\], hors \[4,5 % ; 5,5 %\] | 5 % | 9 % |
| Réduction-restauration | facteur \~ U\[0,82 ; 0,95\] | ×0,8 | ×0,75 |
| Composition | aucune | aucune | rotation −1,25° puis JPEG 65 |
| Interpolation | bilinéaire ou bicubique, tirée au hasard | bicubique | bicubique |

Le jeu scellé est volontairement hors de la plage de développement pour JPEG, bruit et réduction : il mesure l'extrapolation de la sévérité.

**Nombre de tirages.** K = 100 par famille photométrique (JPEG, bruit) pour les étapes 2 à 4a ; K = 50 par famille pour le criblage des descripteurs (étape 4b) ; K = 50 par famille géométrique pour les mesures secondaires.

**Chaînes de décodage.** P0 (image identique), P1 (coordonnées fixes), P2 (ORB/RANSAC, paramètres de 1bis, un recalage en échec compte comme un échec), P3 (inverse oracle). Chemin primaire : P1 (= P3) pour JPEG et bruit ; P2 pour la géométrie, avec P1 et P3 rapportés.

Graines distinctes pour les tirages, les messages, le bruit, RANSAC et la partition ; bibliothèques figées comme en 1bis (Python 3.13.5, OpenCV 4.12.0, NumPy 2.2.6, SciPy 1.17.1) ; un sous-ensemble est rejoué avec une seconde implémentation JPEG et d'interpolation.

## 6. Métriques

La métrique primaire est la justesse sous JPEG 75 et bruit σ = 2 en P3 ; les mesures de plafond décident de l'embranchement.

| Métrique | Définition | Sert à |
| --- | --- | --- |
| a\_P3 | fraction d'octets exacts sous inverse oracle (P1 = P3 pour JPEG et bruit), cas faisables, moyennée par couverture | Q2, Q3, G-T2 |
| ρ | fraction d'emplacements robustes par couverture (zéro basculement sur K tirages par famille) | Q1, Q6, H10 |
| N\_rob(B, n) | faisabilité avec emplacements robustes pour les messages zlib-9 ; n rapporte la longueur comprimée, source 100/200 octets | Q1, H8, G-T1 |
| Couverture des valeurs | nombre de valeurs de hachage (0 à 255) ayant au moins un emplacement robuste à ±B | diagnostic de G-T1 |
| Bits par symbole | coût sérialisé fixe ceil(log₂M)+ceil(log₂(2B+1)) ; H(δ) rapportée séparément comme borne informationnelle | Q3, G-T2 |
| Calibration | écart entre ŝ prédit et basculements observés sur la validation (score de Brier, courbe de fiabilité) ; comparaison de Π ŝ\_j au taux de messages exacts | validité de l'estimation |
| Bits retournés | histogramme par famille de comparaison (zigzag, ligne, colonne, centre contre 8 voisins) et par rang de bit, avec la marge normalisée z\_i au moment du basculement | Q4 |
| Distribution des hachages | nombre de valeurs distinctes et rayon de recouvrement du codebook | Q6, capacité |
| a\_P2, messages exacts | justesse après ORB/RANSAC pour la rotation et le recadrage ; fraction de messages exacts | secondaire |

Le coût dépend de la résolution et du profil : le prototype 512×512/L=12/B=2 coûte 16 bits fixes par symbole ; BOWS2 256×256/L=12/B=2 coûte 14 bits. Tous les tableaux indiquent corpus, M, bits de jeton, bits de résidu et entropie empirique.

```latex
p_{\text{basculement}} \le \frac{3}{K}\ (\text{95 \%}), \qquad P(\text{message exact}) \approx \prod_{j} \hat{s}(\sigma(j))
```

La seconde formule suppose des basculements indépendants ; la mesure de calibration la teste et elle n'est jamais utilisée comme garantie.

## 7. Statistiques et taille d'échantillon

L'unité statistique est la couverture, car les messages d'une même couverture partagent ses emplacements. Les méthodes sont celles de 1bis, pour que les résultats restent comparables.

- **Intervalles.** Bootstrap par grappes sur les couvertures, 10 000 tirages, intervalle à 95 % par percentiles. Intervalles de Wilson pour les taux de faisabilité.
- **Tests.** Test de permutation apparié par inversion de signe, 100 000 tirages, p = (1 + k) / 100 001, plus petit p atteignable ≈ 0,00001 ; correction de Holm par famille d'hypothèses (H8 à H10). Les IC restent la preuve principale ; les p ne sont jamais présentés comme des p bootstrap.
- **Basculements par emplacement.** Zéro basculement sur 100 tirages donne une borne supérieure unilatérale Clopper–Pearson de 2,95 % à 95 % pour une famille donnée. Les familles sont rapportées séparément, sans inférence simultanée.
- **Comparaisons appariées.** Mêmes (couverture, message, perturbation) pour toutes les configurations.
- **Tailles.** Développement D : 200 couvertures (100 pour les étapes 2 et 3). Validation E : 200. Phase C : N = max(200, ⌈(1,96·sd\_Δ / 0,03)²⌉) pour BOWS2-C, avec sd\_Δ estimé sur un pilote de 20 couvertures de BOWS2-E, et 200 pour BOSSBase-F.
- **Messages et agrégation.** Chaque message source de 100 ou 200 octets est compressé une fois par zlib niveau 9 avant affectation ; le nombre de symboles est la longueur comprimée. Les messages primaires de 100 octets comprennent quatre familles × indices 00–02 (12 cas par couverture) ; 200 octets est secondaire. Une couverture satisfait le critère primaire si ses 12 cas sont tous faisables pour le même B. G-T1 utilise la borne basse Wilson 95 % sur les couvertures.
- **Exploratoire contre confirmatoire.** Les étapes 2 à 5 explorent la grille : toutes les cellules sont rapportées et aucune n’est présentée comme confirmation. La sélection est validée sur E, puis confirmée sur C et F uniquement à l’étape 6.
- **Graines.** Une graine par source d'aléa.

## 8. Procédure et budget

La procédure est séquentielle ; chaque étape a un point d'arrêt, et l'étape 3 décide de l'embranchement 4a ou 4b.

| Étape | Contenu | Sortie |
| --- | --- | --- |
| 0 | gel du protocole amendé, commit, réallotissement hash-only C→D/E/C, manifestes D/E/C/F et versions | hash du commit et empreintes des manifestes |
| 1 | préalables V1–V5 ; contrôle des résultats archivés A/B et reprise déterministe des mêmes 20 couvertures A et 20 B (40 au total), mêmes huit messages et transformations, profil L=12/S3 λ=0,5 ; écart ≤0,05 point | barrière G-T0 |
| 2 | diagnostics sur D (100 couvertures) : histogramme des bits retournés, marges, distribution des hachages | tableaux T1, T2 |
| 3 | plafond de la sélection : C3 (emplacements robustes seulement), K = 100 par famille photométrique, B ∈ {2 ; 4 ; 8}, n ∈ {100 ; 200} | barrière G-T1, embranchement |
| 4a | si G-T1 est franchie : optimisation de la sélection (C0 à C2, ε et B balayés) sur D, puis validation sur E | barrière G-T2 |
| 4b | sinon : criblage des descripteurs F5 sur D (K = 50), puis reprise de l'étape 3 pour les deux meilleurs | barrière G-T3 |
| 5 | rapport exploratoire, configuration unique retenue pour la phase C | décision |
| 6 | phase C : BOWS2-C et BOSSBase-F, configuration gelée | feu de phase C |

**Budget de calcul.** Le repère de 428 ms/codebook de l’étape 1 ne se transpose pas aux dimensions natives 256×256 ni à 200 perturbations par couverture. Chronométrer cinq couvertures D par profil/famille et mesurer la mémoire avant l’étape 3 ; publier les temps mesurés, sans extrapolation présentée comme résultat.

- Le nombre de candidats et de tirages de chaque étape est figé dans le journal de calcul après le pilote de cinq couvertures.

**Points d'arrêt.** Arrêt à la fin de chaque étape si sa barrière n'est pas verte. Aucune étape n'ouvre BOWS2-C ni BOSSBase-F avant l'étape 6.

## 9. Barrières et feux

Chaque barrière est fixée avant exécution ; un écart de seuil après coup est consigné comme post hoc.

| Barrière | Condition verte | Orange | Rouge |
| --- | --- | --- | --- |
| G-T0, préalables | V1 à V5 faits ; régression ≤ 0,05 point | V4 impossible à reconstituer (mesure refaite à l'étape 2) | régression > 0,05 point : corriger avant tout |
| G-T1, plafond de sélection | borne basse Wilson 95 % ≥90 % de couvertures satisfaisant les 12 messages source de 100 octets avec les seuls emplacements robustes, pour un même B≤8 : branche 4a | estimation ponctuelle ≥70 % mais borne basse <90 % : 4a et 4b en parallèle | estimation ponctuelle <70 % : branche 4b |
| G-T2, justesse (4a) | sous JPEG75 **et** bruit σ=2, chacun a\_P3≥0,95 et borne basse IC≥0,92 ; coût fixe ≤20 bits/symbole ; validation E | l'un des a\_P3 de 0,90 à 0,95, ou coût 20–24 bits | l'un des a\_P3<0,90 : 4b |
| G-T3, descripteur (4b) | un candidat rend G-T1 verte et passe G-T2 | candidat qui passe G-T1 seulement | aucun candidat : limite documentée |

**Feux de phase C** (configuration gelée, un seul passage) :

- **Vert** : borne basse de l'IC ≥ 0,92 sur BOWS2-C et sur BOSSBase-F pour JPEG 75 et bruit σ = 2 ; rédiger alors le protocole du code correcteur et de la géométrie.
- **Orange** : vert sur un seul corpus, ou écart entre corpus supérieur à 0,05 ; expliquer l'écart avant d'aller plus loin.
- **Rouge** : documenter la limite ; le mode catalogue (univers fermé) reste le mode supporté.

## 10. Menaces à la validité et replis

| Menace | Parade |
| --- | --- |
| Malédiction du vainqueur : la meilleure configuration d'une grille large est optimiste | réévaluation sur E, puis sur C et F, un seul passage |
| Contamination du jeu scellé | pixels de C et de F jamais ouverts ; paramètres du jeu scellé hors des plages de développement |
| Surajustement aux plages JPEG et bruit | trous autour des valeurs de validation ; extrapolation mesurée sur le jeu scellé |
| Représentativité de BOWS2 | second corpus BOSSBase-F ; écart entre corpus rapporté |
| Indépendance dans Π ŝ | test de calibration (section 6) ; jamais utilisé comme garantie |
| Estimation de ŝ avec K petit | lissage, règle de trois, K = 100 ; borne par emplacement seulement |
| Descripteur : valeurs de hachage mal réparties, capacité réduite | distribution des hachages et rayon de recouvrement (section 6) ; capacité comptée dans G-T1 |
| Effets de bibliothèque (JPEG, interpolation) | versions figées ; sous-ensemble rejoué avec une seconde implémentation |
| Géométrie ignorée par les mesures photométriques | mesures secondaires en P2 et P3 ; stabilité géométrique hors du critère de décision |

**Replis.** Si G-T3 est rouge, ou si la phase C est rouge, le mode catalogue (univers fermé, 40/40) reste le mode supporté ; l'article le présente alors comme tel, avec les limites mesurées (récupération exacte ≤ 2,7 % en canal bruité) et sans promesse de robustesse en univers ouvert.

## 11. Livrables

**Fichiers.** Un CSV par ligne (couverture, message, perturbation, configuration) qui reprend le schéma de 1bis et ajoute : famille de coût, ε, B, descripteur, ŝ, robuste (oui/non), bits retournés, bits par symbole. Manifestes SHA-256 des jeux, hash du commit, versions des bibliothèques, graines.

| Tableau | Contenu |
| --- | --- |
| T1 | histogramme des bits retournés par famille de comparaison et rang de bit |
| T2 | marges normalisées au basculement ; distribution des hachages |
| T3 | fraction robuste ρ, N\_rob et couverture des valeurs, par B et n |
| T4 | plafond de sélection (G-T1) avec intervalles |
| T5 | justesse a\_P3 et bits par symbole par coût et ε (frontière) |
| T6 | criblage des descripteurs, le cas échéant |
| T7 | calibration de ŝ ; secondaire P2 et P3 ; messages exacts |

**Figures.** Frontière justesse contre bits par symbole ; courbe de fiabilité de ŝ ; fraction robuste contre B.

**Page de décision.** Une page : feux G-T0 à G-T3, configuration retenue, feu de phase C, écarts avec ce protocole classés comme post hoc, et suite recommandée.
