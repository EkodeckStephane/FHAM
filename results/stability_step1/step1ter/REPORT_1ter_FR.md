# Étape 1ter — rapport exploratoire

**Date :** 18 novembre 2026  
**Branche :** `revision/position-stability-2026-11-15`  
**Protocole gelé :** commit `cf655f8`  
**Partition hash-only :** commit `8d7d9e7`  
**Jeux évalués :** 100 images BOWS2-D; résolution native 256×256.

## Décision en bref

**G-T1 est rouge pour le descripteur spectral; G-T3 est rouge pour les deux meilleurs descripteurs de remplacement.** La sélection d’emplacements robustes améliore nettement la stabilité des positions et la justesse sur les messages effectivement affectables. Elle ne permet toutefois pas d’affecter les 12 messages sur au moins 90 % des couvertures. Le goulot de la campagne reste donc la capacité effective, pas la justesse conditionnelle après affectation.

Selon les portes gelées, aucun candidat n’est retenu pour E. Les pixels d’évaluation de BOWS2-E et BOWS2-C n’ont pas été ouverts; BOSSBase-F n’a servi qu’à l’inventaire hash-only et n’a pas été évalué. La campagne ne passe pas à l’étape 6.

## Contrôles préalables et traçabilité

- **G-T0 passe.** Les 20 couvertures A et 20 couvertures B, les huit messages par couverture, L=12 et S3/λ=0,5 reproduisent exactement les comptes bruts archivés : 4 480 lignes appariées, écart de 0,00 point.
- V1–V5 sont vérifiés à partir des sorties archivées de 1bis. Les détails et les données de contrôle sont dans `G_T0/`.
- Un pilote de cinq couvertures D a été lancé par erreur avant G-T0. Il est conservé sous `results/stability_step1/step2_3_pre_gate/`, exclu des analyses et décisions; les mêmes cinq couvertures ont été recalculées après G-T0 avec les paramètres gelés. Aucun réglage n’a été effectué à partir du pilote prématuré.
- Les images D/E/C ont été réallouées par SHA-256 avant toute métrique. Le manifeste attribue 200 images à D, 200 à E et 7 125 à C. Les 400 images BOSSBase précédemment candidates sont exclues de F; le manifeste F est une réservation hash-only.
- Les messages source de 100 et 200 octets ont été comprimés avec zlib-9 avant affectation. Les métriques indiquent la longueur comprimée et distinguent faisabilité, justesse conditionnelle et justesse effective.

## Étape 2 — stabilité et basculements du hachage spectral

Sur les 100 couvertures D, une position est robuste si son hash ne bascule dans aucun des 100 tirages JPEG ni des 100 tirages bruit.

| Profil | Famille | Basculements / comparaisons | Taux de basculement |
|---|---|---:|---:|
| L=12 | JPEG | 25 554 206 / 141 120 000 | 18,11 % |
| L=12 | Bruit σ∈[1,2,4] | 22 013 685 / 141 120 000 | 15,60 % |
| L=24 | JPEG | 2 851 521 / 32 000 000 | 8,91 % |
| L=24 | Bruit σ∈[1,2,4] | 3 057 749 / 32 000 000 | 9,56 % |

La médiane des médianes de (z_i) aux comparaisons basculées, regroupée sur les arrangements et rangs de bit, vaut 0,729 pour L=12/JPEG, 0,186 pour L=12/bruit, 0,484 pour L=24/JPEG et 0,278 pour L=24/bruit. Les distributions détaillées par arrangement et bit sont dans `step2_z_at_flip/z_at_flip_summary.csv`.

L’audit a corrigé le dénominateur du premier export : chaque bit appartient à un arrangement donné, donc son nombre de comparaisons est calculé sur les positions de cet arrangement, pas sur les quatre arrangements cumulés. Les comptes de basculement de la passe complémentaire concordent exactement avec ceux de l’analyse initiale après cette correction.

## Étape 3 — plafond spectral C3 et G-T1

La fraction médiane de positions robustes est 110/1 764 pour L=12 et 92/400 pour L=24. Le résultat G-T1 porte sur les 12 messages de 100 octets source (quatre familles × trois indices), tous faisables sur la même couverture, avec les seuls emplacements robustes et un même B.

| Profil | B | Couvertures satisfaisant les 12 messages | Estimation | IC Wilson 95 % | G-T1 |
|---|---:|---:|---:|---:|---|
| L=12 | 2 | 0/100 | 0 % | [0,00 ; 3,70] % | Rouge |
| L=12 | 4 | 0/100 | 0 % | [0,00 ; 3,70] % | Rouge |
| L=12 | 8 | 2/100 | 2 % | [0,55 ; 7,00] % | Rouge |
| L=24 | 2 | 0/100 | 0 % | [0,00 ; 3,70] % | Rouge |
| L=24 | 4 | 0/100 | 0 % | [0,00 ; 3,70] % | Rouge |
| L=24 | 8 | 0/100 | 0 % | [0,00 ; 3,70] % | Rouge |

Le seuil préétabli (borne basse ≥90 %) est très loin d’être atteint. L’augmentation de B jusqu’à 8 ne lève pas le plafond de sélection.

## Étape 4b — criblage des descripteurs

Le criblage utilise K=50 essais par famille sur D; un emplacement est robuste s’il ne bascule ni sous JPEG ni sous bruit. Le classement par fraction robuste moyenne est :

| Rang | Descripteur | Fraction robuste moyenne | Positions robustes moyennes | Valeurs de hash robustes distinctes, moyenne |
|---:|---|---:|---:|---:|
| 1 | C-moyenne | 26,12 % | 460,73 | 159,76 |
| 2 | C-DCT | 16,70 % | 294,50 | 128,16 |
| 3 | Arr.4 | 13,58 % | 217,31 | 101,11 |
| 4 | Spectral | 6,81 % | 120,18 | 69,30 |

C-moyenne et C-DCT ont été retenus selon la règle gelée; le score mesure un criblage exploratoire sur D, pas une validation indépendante.

## Répétition du plafond pour C-moyenne et C-DCT

| Descripteur | B | Couvertures satisfaisant les 12 messages | Taux | IC Wilson 95 % | G-T1 |
|---|---:|---:|---:|---:|---|
| C-moyenne | 2 | 15/100 | 15 % | [9,31 ; 23,28] % | Rouge |
| C-moyenne | 4 | 49/100 | 49 % | [39,42 ; 58,65] % | Rouge |
| C-moyenne | 8 | 68/100 | 68 % | [58,34 ; 76,33] % | Rouge |
| C-DCT | 2 | 5/100 | 5 % | [2,15 ; 11,18] % | Rouge |
| C-DCT | 4 | 26/100 | 26 % | [18,40 ; 35,37] % | Rouge |
| C-DCT | 8 | 47/100 | 47 % | [37,51 ; 56,71] % | Rouge |

C-moyenne améliore nettement la faisabilité, mais son meilleur résultat (68 %) reste sous le seuil orange de 70 % et sous la borne basse requise de 90 %. C-DCT ne dépasse pas 47 %.

## Justesse après affectation et récupération exacte

Pour les messages qui ont une affectation, la justesse de symbole reste élevée sous JPEG 75 et bruit σ=2 : au moins 99,25 % pour C-DCT et 99,51 % pour C-moyenne parmi les couvertures comportant une affectation faisable à B=8. Ces taux conditionnels ne mesurent pas la proportion des tentatives qui aboutissent.

En comptant les tentatives non faisables comme une absence de récupération, à B=8 et pour les messages source de 100 octets :

| Descripteur | Canal | Justesse effective | IC cluster-bootstrap 95 % | Messages comprimés exacts / tentatives |
|---|---|---:|---:|---:|
| C-moyenne | JPEG 75 | 77,74 % | [69,87 ; 84,95] % | 67,00 % |
| C-moyenne | Bruit σ=2 | 77,64 % | [69,77 ; 84,81] % | 62,00 % |
| C-DCT | JPEG 75 | 61,19 % | [52,61 ; 69,49] % | 43,83 % |
| C-DCT | Bruit σ=2 | 61,37 % | [52,79 ; 69,72] % | 52,00 % |

La séparation entre **justesse conditionnelle** et **succès de communication effectif** est donc déterminante : les symboles sont récupérés avec grande précision lorsque le message peut être affecté, mais beaucoup de couvertures n’acceptent pas l’ensemble demandé.

## Feux et suites

- **G-T0 : vert.**
- **G-T1 spectral : rouge.**
- **Classement descripteurs :** C-moyenne puis C-DCT sur D.
- **G-T1 pour les deux candidats : rouge.**
- **G-T2 :** la justesse conditionnelle parmi les affectations faisables est élevée; la justesse effective et la faisabilité ne satisfont pas les seuils de réussite du protocole.
- **G-T3 : rouge.** Aucun descripteur n’est retenu pour validation E selon les critères gelés.
- **Étape 6 : non ouverte.** C/F restent réservés; aucune donnée d’évaluation scellée n’est consultée.

## Conséquence pour la révision de l’article

Ces résultats ne justifient pas d’affirmer que la sélection seule rend FHAM robuste ou opérationnellement viable en canal photométrique. Ils soutiennent plutôt deux observations circonscrites : (i) une pondération par stabilité et le descripteur de moyenne augmentent la récupération conditionnelle; (ii) la capacité effective, mesurée par l’affectation complète des messages, reste insuffisante sous le seuil préenregistré. L’article devra présenter les deux métriques côte à côte et qualifier ces configurations comme exploratoires, sans les présenter comme une version validée.
