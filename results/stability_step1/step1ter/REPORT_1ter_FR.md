# Étape 1ter — résultats exploratoires et audit des diagnostics

**Date :** 18 novembre 2026
**Branche :** `revision/position-stability-2026-11-15`
**Protocole gelé :** commit `cf655f8`; amendement de partition hash-only : `8d7d9e7`
**Données analysées :** 100 images BOWS2-D, résolution native 256×256.
**Portée :** résultats exploratoires de cette campagne seulement. BOWS2-E, BOWS2-C et BOSSBase-F ne sont pas des jeux d’évaluation ouverts dans cette étape.

## 1. Conclusion circonscrite

Sur les images BOWS2-D en 256×256 et les paramètres préenregistrés, le descripteur de moyenne augmente le nombre de messages affectables par rapport au descripteur spectral. À B=8, 68/100 couvertures acceptent simultanément les 12 messages de 100 octets source avec les seuls emplacements robustes; la borne basse de Wilson est 58,34 %. Ce résultat est inférieur à la porte G-T1 (borne basse ≥90 %). Il décrit cette configuration, cette résolution, ces messages et ces images; il ne démontre pas un plafond structurel indépendant de la résolution ou du protocole d’émission.

Les positions robustes donnent une justesse de symbole conditionnelle élevée une fois l’affectation réalisable. La faisabilité reste dépendante du contenu du message et de la couverture. Les métriques « faisabilité par message », « faisabilité conjointe des 12 messages », « justesse conditionnelle » et « récupération exacte » sont rapportées séparément ci-dessous.

## 2. Résolution, profils et nombre de positions

Le protocole gelé spécifie BOWS2-D/E/C natif en 256×256 et BOSSBase-F natif en 512×512, sans redimensionnement pour les mesures de plafond. Le script de plafond vérifie que chaque image BOWS2 chargée a la forme `(256, 256)` et s’arrête sinon. La convention des blocs non chevauchants donne, avec quatre arrangements :

| Corpus et profil | Positions M à L=12 | Positions M à L=24 | Bits fixes par symbole à L=12, B=8 |
|---|---:|---:|---:|
| BOWS2, 256×256 | 1 764 | 400 | 16 (11 jeton + 5 résidu) |
| BOSSBase, 512×512 | 7 056 | 1 764 | 18 (13 jeton + 5 résidu) |

Ainsi, 7 056 positions à L=12 correspond à BOSSBase 512×512; 1 764 positions à L=12 correspond à BOWS2 256×256. Ce sont deux configurations distinctes. Les résultats G-T3 ci-dessous concernent BOWS2-D à 256×256; ils ne sont pas extrapolés à 512×512.

Le coût fixe est `ceil(log2 M) + ceil(log2(2B+1))`. Le tableau complet pour L=12/24 et B=2/4/8, ainsi que les profils BOSSBase, est fourni dans `audit_diagnostics/fixed_bits_by_profile.csv`.

## 3. Contrôles et stabilité du descripteur spectral

G-T0 reproduit les résultats archivés de 1bis sur 20 images A et 20 images B : 4 480 lignes appariées, écart de 0,00 point. Un pilote de cinq images exécuté avant le contrôle G-T0 est conservé séparément et exclu des analyses; ces cinq images ont été recalculées après le contrôle avec les paramètres gelés.

Sur les 100 images D, les taux de basculement des comparaisons spectrales étaient :

| Profil | Perturbation | Basculements / comparaisons | Taux |
|---|---|---:|---:|
| L=12 | JPEG | 25 554 206 / 141 120 000 | 18,11 % |
| L=12 | bruit σ∈[1,2,4] | 22 013 685 / 141 120 000 | 15,60 % |
| L=24 | JPEG | 2 851 521 / 32 000 000 | 8,91 % |
| L=24 | bruit σ∈[1,2,4] | 3 057 749 / 32 000 000 | 9,56 % |

La fraction médiane de positions robustes était 110/1 764 à L=12 et 92/400 à L=24. Le premier export du taux de basculement avait un dénominateur quatre fois trop grand; les résultats ci-dessus utilisent le dénominateur corrigé par arrangement. La passe indépendante des marges reproduit les comptes de basculement.

## 4. Faisabilité du plafond spectral

G-T1 a été défini sur la faisabilité conjointe des 12 messages (quatre familles × trois indices) de 100 octets source, comprimés séparément par zlib-9. Cette conjonction est bien le critère préenregistré de la campagne. Elle ne remplace pas les taux par message, également exportés dans `audit_diagnostics/per_message_feasibility.csv`.

| Profil | B | Couvertures faisables pour les 12 messages | IC Wilson 95 % |
|---|---:|---:|---:|
| L=12 | 2 | 0/100 | [0,00 ; 3,70] % |
| L=12 | 4 | 0/100 | [0,00 ; 3,70] % |
| L=12 | 8 | 2/100 | [0,55 ; 7,00] % |
| L=24 | 2 | 0/100 | [0,00 ; 3,70] % |
| L=24 | 4 | 0/100 | [0,00 ; 3,70] % |
| L=24 | 8 | 0/100 | [0,00 ; 3,70] % |

## 5. Descripteurs et faisabilité par message

Le criblage de D (K=50, profil L=12) classe les descripteurs par fraction moyenne de positions robustes :

| Descripteur | Fraction robuste moyenne | Positions robustes moyennes | Valeurs de hash robustes distinctes, moyenne |
|---|---:|---:|---:|
| C-moyenne (`mean_ordinal`) | 26,12 % | 460,73 | 159,76 |
| C-DCT (`dct_sumabs`) | 16,70 % | 294,50 | 128,16 |
| Arr.4 | 13,58 % | 217,31 | 101,11 |
| Spectral | 6,81 % | 120,18 | 69,30 |

Pour les messages individuels de 100 octets source à B=8, le taux de couvertures faisables varie comme suit (moyenne des trois indices de chaque famille) :

| Descripteur | Octets uniformes | ASCII imprimable | Texte naturel | Octet répété |
|---|---:|---:|---:|---:|
| C-moyenne | 79,7 % | 73,7 % | 79,0 % | 93,0 % |
| C-DCT | 65,0 % | 54,0 % | 63,3 % | 86,7 % |

Les taux détaillés pour chaque indice sont dans `audit_diagnostics/per_message_feasibility.csv`. Le critère conjoint des 12 cas reste plus exigeant : C-moyenne atteint 15 %, 49 % et 68 % pour B=2, 4 et 8; C-DCT atteint 5 %, 26 % et 47 %. Les intervalles Wilson à 95 % sont conservés dans les tableaux de résultats de plafond et les données brutes `step4b_ceiling/`.

Les sorties contiennent des messages de 100 et 200 octets source. Elles ne contiennent pas une courbe préenregistrée n={25,50,100,200} ni une capacité maximale calculée pour chaque couverture. On ne déduit donc pas de capacité maximale continue à partir de deux longueurs testées. Cette courbe nécessiterait une mesure séparée prévue et gelée dans 1quater.

## 6. Histogrammes robustes et couverture des valeurs cibles

Les histogrammes par valeur de hash 0–255, pour L=12, sont fournis dans `audit_diagnostics/robust_hash_histogram.csv`. Pour rendre le diagnostic interprétable, le tableau suivant compte, parmi les 25 600 paires (couverture D, valeur cible), la part pour laquelle aucun emplacement robuste n’a de hash à distance ≤B. Il rapporte aussi le nombre moyen de positions candidates dans ce voisinage. Cette mesure est un diagnostic marginal; elle ne constitue pas le test de Hall, qui porte sur les voisinages de sous-ensembles de symboles et sur l’injectivité.

| Descripteur | B | Paires couverture-cible sans candidat | Cibles sans candidat sur les 100 couvertures | Candidats moyens par cible et couverture |
|---|---:|---:|---:|---:|
| C-moyenne | 2 | 6,16 % | 0 | 8,822 |
| C-moyenne | 4 | 2,77 % | 0 | 15,801 |
| C-moyenne | 8 | 1,01 % | 0 | 29,650 |
| C-DCT | 2 | 12,73 % | 0 | 5,587 |
| C-DCT | 4 | 6,76 % | 0 | 9,994 |
| C-DCT | 8 | 3,34 % | 0 | 18,734 |
| Spectral | 2 | 31,37 % | 0 | 2,215 |
| Spectral | 4 | 18,16 % | 0 | 3,945 |
| Spectral | 8 | 9,21 % | 0 | 7,376 |

Dans cet échantillon, aucun octet cible n’est dépourvu de voisin robuste sur les 100 couvertures à la fois. Cela n’implique pas que chaque couverture contienne des candidats pour tous les octets, ni que les messages soient affectables : les collisions d’usage des positions et les contraintes de Hall peuvent encore rendre une affectation impossible. Les comptes exacts par octet et par B figurent dans `audit_diagnostics/robust_hash_neighborhood_coverage.csv`.

## 7. Justesse conditionnelle et récupération

À B=8, parmi les messages affectables, la justesse conditionnelle par symbole sous JPEG 75 ou bruit σ=2 est au moins 99,51 % pour C-moyenne et 99,25 % pour C-DCT. En comptant les tentatives infaisables comme des échecs de communication, la justesse effective vaut :

| Descripteur | Canal | Justesse effective | IC cluster-bootstrap 95 % | Messages comprimés exacts / tentatives |
|---|---|---:|---:|---:|
| C-moyenne | JPEG 75 | 77,74 % | [69,87 ; 84,95] % | 67,00 % |
| C-moyenne | Bruit σ=2 | 77,64 % | [69,77 ; 84,81] % | 62,00 % |
| C-DCT | JPEG 75 | 61,19 % | [52,61 ; 69,49] % | 43,83 % |
| C-DCT | Bruit σ=2 | 61,37 % | [52,79 ; 69,72] % | 52,00 % |

La justesse conditionnelle ne mesure ni le taux d’affectation, ni la récupération exacte. Ces trois grandeurs sont distinctes.

## 8. État des portes et portée pour l’article

- G-T0 : vert.
- G-T1 : rouge pour le spectral et pour les candidats C-moyenne/C-DCT sur la campagne D et le critère conjoint gelé.
- G-T3 : rouge; aucun candidat n’est sélectionné pour validation E selon les portes du protocole.
- E et C restent fermés; BOSSBase-F n’a pas fait l’objet d’une évaluation de plafond dans cette étape.

La formulation à retenir est limitée aux configurations évaluées : C-moyenne améliore la faisabilité observée et la justesse conditionnelle sur BOWS2-D 256×256, mais le critère conjoint G-T1 n’est pas satisfait. L’effet d’une couverture 512×512, d’une sélection parmi plusieurs couvertures, du remplissage robuste/non robuste sous contrainte ou du découpage du message n’est pas établi par 1ter. Ces leviers relèvent d’un protocole 1quater, avec nouveau gel avant toute mesure. Le mode catalogue demeure le mode supporté dans l’article tant qu’une synchronisation et une transmission générales ne sont pas validées.

Les présentes observations servent à délimiter les résultats de révision; elles ne modifient pas les données ou seuils de la campagne préenregistrée.
