# Étape 2 — Résultats P4 sur D-b

**Date d’exécution :** 23 novembre 2026  
**Statut :** extension post hoc exploratoire, menée à la demande de l’auteur après le point d’arrêt initial G2.  
**Protocole :** `protocols/FHAM_etape_2_extension_posthoc_P4_sealed_2026-11-21.md`, amendement de chronométrage du 21 novembre.  
**Runner P4 SHA-256 :** `4e421c9e9ce64e7de443f3a8b5c67e9954add4bbeaa8fd8ad6e70e5e236887db`  
**Commit ayant produit les mesures :** `22c822a`; le script de métriques descriptives a ensuite été ajouté au commit `4ed6666`.

## Plan et contrôle de complétude

D-b comprend les quatre messages gelés — `adversarial_repeated`, `natural_text`, `printable_ascii` et `uniform_bytes` — avec 100 tentatives de galerie par message, soit 400 tentatives et 1 200 cellules message-transformation-chaîne. Les tentatives infaisables restent dans les dénominateurs. Aucune image de E-geo, C-geo ou F-geo n’a été ouverte pour ces mesures.

L’affectation était faisable dans 387/400 tentatives (96,75 %). Le détail est de 100 % pour le message répétitif, 95 % pour le texte naturel, 93 % pour l’ASCII imprimable et 99 % pour les octets uniformes. Les 387 tentatives faisables fournissent 774 segments et 2 322 observations segment-transformation. ORB/RANSAC a réussi sur tous les segments faisables de D-b.

Le contrôle croisé de P1, P2 et P3 avec les sorties G2 retrouve exactement les mêmes valeurs dans les 3 483 cellules communes (3 chaînes × 3 transformations × 387 tentatives faisables). Aucun écart n’a été observé.

## Récupération exacte du message

Les intervalles sont des IC bootstrap à 95 % groupés par couverture. Les taux incluent les tentatives de galerie infaisables.

| Transformation | P1, coordonnées fixes | P2, ORB/RANSAC | P3, inverse oracle | P4, recherche locale |
|---|---:|---:|---:|---:|
| Recadrage-restauration | 0,00 % | 0,75 % [0,00 ; 2,55] | 1,75 % [0,00 ; 4,35] | 0,75 % [0,00 ; 2,53] |
| Rotation | 0,25 % | 10,50 % [5,10 ; 16,06] | 12,25 % [6,58 ; 17,78] | 10,50 % [5,12 ; 15,94] |
| Redimensionnement-restauration | 91,50 % | 89,75 % [78,51 ; 93,08] | 91,50 % [80,74 ; 94,29] | 89,75 % [78,48 ; 93,05] |

P4 ne dépasse pas P3 sur ces mesures D-b. P4 reproduit le taux P2 en rotation et redimensionnement, et le taux P2 en recadrage. La synchronisation géométrique reste donc non résolue pour le profil évalué.

## Dépendance à la famille du message

Taux de récupération exacte sous P4, sur 100 tentatives par famille :

| Famille | Recadrage | Rotation | Redimensionnement |
|---|---:|---:|---:|
| Répétition adversariale | 3 % | 36 % | 97 % |
| Texte naturel | 0 % | 0 % | 88 % |
| ASCII imprimable | 0 % | 3 % | 84 % |
| Octets uniformes | 0 % | 3 % | 90 % |

La moyenne agrégée masque ainsi une forte dépendance à la distribution des symboles. Le résultat favorable en rotation est propre au message répétitif de cet échantillon; il ne se généralise pas aux autres familles testées.

## Calcul et comportement de P4

Le budget corrigé est de 60 secondes CPU actives par cellule message-transformation, partagé entre les deux segments et incluant ORB/RANSAC. Le temps CPU et le temps mural sont consignés séparément. Aucune cellule D-b n’a dépassé 60 secondes CPU; la durée CPU maximale par segment était de 3,46 s. Aucune recherche n’a été interrompue par le budget.

Le nombre moyen de candidats évalués par tentative (les cellules infaisables contribuent zéro) est de 1 164,1 pour le recadrage, 856,8 pour la rotation et 45,6 pour le redimensionnement. Les durées moyennes CPU/murales correspondantes sont 4,11/4,17 s, 3,24/3,29 s et 0,83/0,84 s.

## Métriques segment et symbole

La faisabilité, l’exactitude segment, les effacements, les erreurs de symbole, l’exactitude parmi les symboles affectés et les temps P4 sont consignés dans `results/step2/geometry/p4_D_b_posthoc_complete_metrics.csv`. L’exactitude symbole est calculée avant Reed–Solomon sur les symboles affectés. Pour P4, elle décrit le candidat gagnant si le segment est exact; sinon, elle décrit le dernier candidat vérifié avant l’arrêt de la grille. Le résultat principal de communication reste l’exactitude du message recomposé avec validation de I1.

## Incident de chronométrage et intégrité des résultats

Un passage antérieur a subi des durées murales supérieures au plafond, compatibles avec une suspension ou un blocage de l’hôte. Il a été conservé séparément sous `results/step2/geometry/pre_cpu_cap_D_b/` avec son journal d’incident et n’est pas intégré aux résultats présents. D-b a été recalculé entièrement sous le budget CPU actif avant l’ouverture des jeux scellés.

## Fichiers de résultats

- `results/step2/geometry/p4_D_b_posthoc_metadata.json` — manifeste, runner, commit et chronométrage.
- `results/step2/geometry/p4_D_b_posthoc_message_trials.csv` — 4 800 lignes message-chaîne-transformation.
- `results/step2/geometry/p4_D_b_posthoc_segment_trials.csv.gz` — 2 322 lignes segment-transformation.
- `results/step2/geometry/p4_D_b_posthoc_summary.csv` — taux exacts et IC bootstrap.
- `results/step2/geometry/p4_D_b_posthoc_complete_metrics.csv` — mesures message, segment, symbole, effacements et calcul.

