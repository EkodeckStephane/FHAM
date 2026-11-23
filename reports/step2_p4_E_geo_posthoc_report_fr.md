# P4 post hoc — E-geo (BOWS2-C)

**Date d’exécution :** 23 novembre 2026  
**Portée :** extension exploratoire post hoc, distincte du protocole Étape 2 v1.2  
**Manifeste SHA-256 :** `f932eccd1dbef7cb4290891e3b7ea9b80d0eccb50c0d96cb12d5b93c22ef48aa`  
**Runner SHA-256 :** `57f0ea2301ed169e1e1bf26185e9961a6a7ab7a0e563c2daec85d72ca520bfef`

## Résultat

E-geo comprend 200 couvertures BOWS2-C à leur résolution native de 256 × 256, quatre messages gelés de 100 octets et 100 tirages de galerie par message. Les 400 tirages ont tous été conservés; 385/400 (96,25 %) ont permis une affectation. Les 12 cellules par tirage (trois transformations × quatre chaînes) donnent 4 800 lignes de résultats message.

| Transformation | P1 coordonnées fixes | P2 ORB/RANSAC | P3 inverse exact | P4 recherche locale |
|---|---:|---:|---:|---:|
| Crop-restauration | 0/400 (0 %) | 0/400 (0 %) | 6/400 (1,50 %; IC 95 % [0; 3,84]) | 0/400 (0 %) |
| Rotation | 0/400 (0 %) | 60/400 (15,00 %; [8,72; 21,46]) | 67/400 (16,75 %; [10,22; 23,47]) | 60/400 (15,00 %; [8,67; 21,53]) |
| Réduction-restauration | 375/400 (93,75 %; [82,90; 95,56]) | 372/400 (93,00 %; [82,08; 95,12]) | 375/400 (93,75 %; [83,04; 95,64]) | 372/400 (93,00 %; [81,98; 95,26]) |

Les intervalles sont des IC bootstrap à 95 % par couverture, calculés par le résumeur gelé. ORB/RANSAC a réussi pour 100 % des segments évalués. Ce recalage ne suffit donc pas à assurer la récupération exacte après rotation ou crop. P4 ne dépasse pas P3 sur ces trois transformations dans E-geo; pour crop, sa récupération exacte est nulle alors que P3 récupère 6 messages.

La récupération par famille confirme une forte dépendance au contenu. Pour P4 sous rotation, les taux sont de 39 % (répétition adversariale), 11 % (texte naturel), 9 % (ASCII imprimable) et 1 % (octets uniformes). Sous réduction-restauration, ils sont respectivement 100 %, 89 %, 87 % et 96 %. Ces taux ne décrivent que les quatre messages choisis et ne généralisent pas à toutes les distributions de même famille.

## Coût de P4 et intégrité d’exécution

P4 a testé en moyenne 1 175 candidats/message pour crop, 766 pour rotation et 22 pour réduction-restauration. Le temps CPU maximal observé par segment est 4,58 s, sous la limite de 60 s CPU actifs par cellule message-transformation. Temps mural et CPU sont conservés séparément dans les données brutes.

Vérifications de complétude : 4 800 lignes message; 400 observations pour chaque cellule transformation-chaîne; 2 310 lignes segment; 200 codebooks; aucune image de remplacement. Les SHA du manifeste et du runner correspondent aux valeurs gelées. Toutes les tentatives infaisables restent dans le dénominateur.

Deux interruptions logicielles préalables à cette exécution complète sont consignées dans `p4_E_geo_incidents.json` et dans le protocole. La première n’a ouvert aucun pixel; la seconde s’est arrêtée à la première écriture de codebook. Elles ne sont pas comptées parmi les mesures. L’évaluation complète utilise le correctif gelé avant la reprise et les mêmes sélections déterministes.

## Conclusion circonscrite

Sur ce jeu exploratoire BOWS2-C et ces conditions, la recherche P4 ne lève pas la limite géométrique sous rotation ou crop; P3 reste légèrement meilleur en récupération exacte. La réduction-restauration demeure le cas favorable, avec 93 % de récupération exacte sous P4. Ces résultats justifient de garder la synchronisation géométrique comme limite du profil actuel. Ils ne constituent ni une validation confirmatoire, ni une preuve d’impossibilité d’améliorations avec un autre descripteur ou un protocole de synchronisation différent.

## Artefacts

- `results/step2/geometry/p4_E_geo_message_trials.csv` — 4 800 résultats message.
- `results/step2/geometry/p4_E_geo_segment_trials.csv.gz` — 2 310 résultats segment.
- `results/step2/geometry/p4_E_geo_summary.csv` — résumé par famille, transformation et chaîne.
- `results/step2/geometry/p4_E_geo_complete_metrics.csv` — métriques complètes au niveau symbole et P4.
- `results/step2/geometry/p4_E_geo_metadata.json` — statut, provenance, paramètres et empreintes.
- `results/step2/geometry/p4_E_geo_incidents.json` — journal des incidents préalables.
