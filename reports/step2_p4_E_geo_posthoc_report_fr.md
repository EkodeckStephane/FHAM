# Étape 2 — résultats P4 sur E-geo

**Date d’exécution :** 23 novembre 2026  
**Statut :** extension exploratoire post hoc; les résultats ne constituent pas une validation confirmatoire du protocole initial.  
**Protocole :** `protocols/FHAM_etape_2_extension_posthoc_P4_sealed_2026-11-21.md`  
**Manifeste E-geo SHA-256 :** `f932eccd1dbef7cb4290891e3b7ea9b80d0eccb50c0d96cb12d5b93c22ef48aa`  
**Runner SHA-256 :** `57f0ea2301ed169e1e1bf26185e9961a6a7ab7a0e563c2daec85d72ca520bfef`  
**Commit du runner :** `565161f61c62055aaa4de4e80eebeb74736bb1fd`

## Exécution et intégrité

Le premier lancement n’a sélectionné aucun message et n’a lu aucun pixel. Le deuxième a ouvert E-geo, puis s’est arrêté lors de l’écriture du premier codebook, avant toute tentative de message. Ces deux incidents sont consignés dans `results/step2/geometry/p4_E_geo_incidents.json`; leurs sorties vides ne sont pas incluses dans les résultats.

Le passage corrigé a utilisé le manifeste hash-only gelé, le même ensemble de messages, la même grille P4, les mêmes graines et l’ordre déterministe préenregistré dans l’extension. Il s’est terminé avec le statut `completed`. Les quatre messages ont chacun 100 tentatives de galerie. Le tableau message contient 4 800 lignes (400 tentatives × 3 transformations × 4 chaînes P1–P4); les tentatives infaisables restent dans les dénominateurs. Le taux de faisabilité des affectations est de 96,25 % (385/400). Le SHA-256 du manifeste correspond à celui attendu par le runner.

## Récupération exacte du message

Les intervalles sont des IC bootstrap à 95 % par grappes de couvertures, tels que calculés par le runner. La barrière G-G2 porte sur la borne basse de l’exactitude message P4 pour chacune des trois familles de transformations.

| Transformation | P1, coordonnées fixes | P2, ORB/RANSAC | P3, inverse oracle | P4, recherche locale |
|---|---:|---:|---:|---:|
| Recadrage-restauration | 0,00 % [0,00 ; 0,00] | 0,00 % [0,00 ; 0,00] | 1,50 % [0,00 ; 3,84] | 0,00 % [0,00 ; 0,00] |
| Rotation | 0,00 % [0,00 ; 0,00] | 15,00 % [8,72 ; 21,46] | 16,75 % [10,22 ; 23,47] | 15,00 % [8,67 ; 21,53] |
| Redimensionnement-restauration | 93,75 % [82,90 ; 95,56] | 93,00 % [82,08 ; 95,12] | 93,75 % [83,04 ; 95,64] | 93,00 % [81,98 ; 95,26] |

## Résultats P4 par famille de message

| Famille | Recadrage-restauration | Rotation | Redimensionnement-restauration |
|---|---:|---:|---:|
| Répétition adversariale | 0 % | 39 % [22,83 ; 58,00] | 100 % [100 ; 100] |
| Texte naturel | 0 % | 11 % [2,40 ; 22,00] | 89 % [67,50 ; 95,50] |
| ASCII imprimable | 0 % | 9 % [1,19 ; 19,30] | 87 % [64,24 ; 94,83] |
| Octets uniformes | 0 % | 1 % [0 ; 5,71] | 96 % [79,13 ; 100] |

La moyenne agrégée masque donc une forte dépendance au type de message pour la rotation et le redimensionnement. Le recadrage ne donne aucune récupération exacte P4 dans les 400 tentatives.

## Barrière G-G2

Le seuil gelé est une borne basse de l’IC à 95 % d’au moins 0,80 pour au moins deux des trois familles de transformations. Une seule famille le satisfait : le redimensionnement-restauration (borne basse P4 : 0,8198). La rotation (0,0867) et le recadrage (0,0000) échouent au seuil.

**Verdict G-G2 : orange** — une seule famille sur trois atteint le seuil. Selon le point d’arrêt du protocole, cette barrière n’autorise pas l’ouverture de C-geo ou F-geo. La présente mesure étant post hoc, ce verdict est un diagnostic exploratoire et ne remplace pas une validation confirmatoire préenregistrée.

### Incident C-geo après le verdict

Après l’évaluation G-G2, C-geo a été ouvert à 09:30:23 UTC. Avant que le garde-fou orange soit visible dans le runner, une première exécution s’est arrêtée avec 184/200 codebooks; une reprise a créé les 200 codebooks et quatre archives d’affectation. Des sorties partielles contiennent 14 tentatives message complètes au sens du format de ligne (11 pour le message répété, une pour chacun des trois autres messages), sans couverture suffisante pour une estimation. Elles ne constituent pas une mesure P4 exploitable et sont exclues des résultats. Le point d’arrêt orange est maintenant appliqué : C-geo ne sera pas relancé et F-geo reste fermé. Les artefacts partiels et les interruptions sont conservés dans `results/step2/geometry/p4_C_geo_*` et détaillés dans `results/step2/geometry/p4_C_geo_incidents.json`.

## Coût P4 et artefacts

Le nombre moyen de candidats P4 par tentative est de 1 175,0 pour le recadrage, 766,3 pour la rotation et 22,2 pour le redimensionnement. Le temps CPU moyen par tentative est respectivement de 3,61 s, 2,57 s et 0,65 s. Aucune cellule message-transformation n’a dépassé le budget CPU actif gelé de 60 s.

- `results/step2/geometry/p4_E_geo_metadata.json` — statut, commit, runner et manifeste.
- `results/step2/geometry/p4_E_geo_gallery_trials.csv` — tirages de galerie et faisabilité.
- `results/step2/geometry/p4_E_geo_message_trials.csv` — résultats message.
- `results/step2/geometry/p4_E_geo_segment_trials.csv.gz` — résultats segment et symbole.
- `results/step2/geometry/p4_E_geo_summary.csv` — taux et IC bootstrap.
- `results/step2/geometry/p4_E_geo_complete_metrics.csv` — faisabilité, exactitude segment, effacements, erreurs et coût.
- `results/step2/geometry/p4_E_geo_incidents.json` — journal des deux lancements avortés.
