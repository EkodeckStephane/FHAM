# Extension post hoc FHAM — P4 et validation géométrique élargie

**Date : 21 novembre 2026.** Cette extension est décidée après les résultats G-2 initiaux, à la demande de l’auteur. Elle ne modifie ni le protocole v1.2 gelé ni ses résultats. Toute mesure ci-dessous est exploratoire et post hoc ; elle ne peut être présentée comme une validation confirmatoire du protocole initial.

## 1. Objet

Poursuivre l’étude de la synchronisation malgré le plafond observé sous inverse géométrique exact, afin de mesurer l’apport de la recherche P4, les résultats par transformation et leur variation entre BOWS2 et BOSSBase. L’extension rapporte les succès partiels et les échecs, sans écarter les cellules défavorables.

## 2. Format, données et séparation

- Le format V1, le descripteur `mean_ordinal` (L=12), la configuration 1quater (`p=10 %`, `q=5 %`, `m=2`, `B=4`), les quatre messages 100 octets déjà gelés et les transformations de l’étape 2 v1.2 restent inchangés.
- Le régime est G-ref : le destinataire dispose de la couverture canonique prépartagée, estime une similarité ORB/RANSAC, puis recherche autour de cette estimation.
- D-b sert uniquement à mettre au point et à mesurer P4. E-geo, C-geo et F-geo sont tirés par manifeste hash-only, gelés avant ouverture des pixels, puis évalués une fois chacun. Tous les résultats E/C/F sont post hoc au regard du point d’arrêt v1.2.
- E-geo et C-geo tirent chacun 200 couvertures du partage BOWS2-C, après exclusion des 200 images C de 1quater et l’un de l’autre. F-geo tire 200 images BOSSBase après exclusion des 400 candidates antérieures, des 200 images F de 1quater et des quasi-doublons déjà signalés. Chaque manifeste conserve les SHA-256 et indique `pixels_opened=false` avant la mesure.
- Les images et messages ne sont pas remplacés si un chemin ou une empreinte échoue. Le corpus défaillant est rapporté comme incomplet.
- Chaque corpus utilise 100 tirages de galerie par message, comme les 100 tentatives A4 de D-b. L’ordre des candidats est une permutation PCG64 générée par `SHA256("FHAM-step2-P4-posthoc|20261121|<corpus>|<message_id>|<segment>|<attempt>")`, premiers 64 bits en big-endian. Les transformations réutilisent le générateur déterministe G2 `SHA256("FHAM-G2|<image_sha256>|<attempt>")`. Toutes les tentatives, y compris infaisables, sont comptabilisées.

## 3. Grille P4 locale

P4 estime d’abord la similarité ORB/RANSAC entre l’image canonique et l’image reçue. Pour chaque segment, il évalue les transformations voisines de l’estimation :

- erreur d’angle : `{−0,50°, −0,25°, 0°, +0,25°, +0,50°}` ;
- facteur d’échelle relatif : `{0,90; 0,95; 1,00; 1,05; 1,10}` ;
- décalage x et y : `{−4, −2, 0, +2, +4}` pixels à 256×256, multiplié par 2 à 512×512.

La grille contient 625 candidats par segment et 1 250 au plus pour les deux segments d’un message, sous le plafond de 2 000 candidats. Les candidats sont examinés dans l’ordre croissant de la somme des carrés des offsets normalisés, puis dans l’ordre lexicographique `(angle, échelle, dx, dy)`. Les doublons numériques sont supprimés et le nombre effectif est rapporté. Si ORB/RANSAC échoue, P4 échoue pour cette image et aucun recentrage oracle n’est utilisé.

À chaque candidat, le récepteur applique l’inverse de la similarité à l’image transformée, relit les seules positions inscrites dans le record, applique Reed–Solomon et vérifie le segment reconstruit. Un message n’est exact que si les deux segments sont exacts et que le digest I1 du message recomposé correspond. Le temps est mesuré du début du recalage à la dernière vérification, avec un plafond de 60 secondes par message. P4 renvoie le premier candidat exact ; le nombre de candidats testés et le rang du candidat sont enregistrés.

## 4. Gel après le développement D-b

Avant toute ouverture d’E/C/F, le rapport D-b consigne : le code exact, la grille effective, les transformations, les graines, le coût par candidat, les réussites, les échecs et les empreintes SHA-256. La grille ci-dessus ne peut être élargie après consultation d’E/C/F. Une panne logicielle peut être corrigée avec un journal d’incident ; elle ne permet pas de changer les paramètres.

## 5. Ordre et compte rendu

1. Générer et committer les manifestes hash-only E-geo, C-geo et F-geo.
2. Mesurer le bassin contrôlé et P4 sur D-b ; geler l’implémentation et les résultats.
3. Ouvrir E-geo, puis C-geo, puis F-geo, une fois chacun, sans modification de grille.
4. Pour P1, P2, P3 et P4, rapporter exactitude message, exactitude segment, précision symbole, effacements, erreurs, recalages échoués, temps et nombre de candidats, avec IC bootstrap par image.
5. Rapporter les familles séparément ainsi que le résultat agrégé. Pas d’extrapolation entre corpus ni de revendication de synchronisation robuste générale.

## 6. Interprétation

Ces mesures évaluent si une recherche locale apporte un gain empirique après recalage. Elles ne changent pas rétroactivement le point d’arrêt initial. Tout résultat positif est un résultat exploratoire à confirmer dans une nouvelle étude préenregistrée ; un échec demeure un résultat scientifique pertinent.
