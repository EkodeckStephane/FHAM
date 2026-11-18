# G-Q0 — audit post hoc du déficit d’affectation

**Date :** 18 novembre 2026
**Statut :** diagnostic descriptif post hoc sur BOWS2-D; aucune nouvelle perturbation, aucun pixel relu.
**Entrées :** positions robustes et étiquettes de faisabilité archivées en 1ter; messages zlib-9 déjà utilisés.
**Script :** `scripts/audit_step1quater_gq0.py`.

## Résumé

Le déficit a été calculé comme `d = n − taille du couplage maximal`, où `n` est la longueur du message comprimé effectivement affecté. Il est séparé en `d_vide` (symboles sans aucune position robuste candidate à ±B) et `d_Hall = d − d_vide` (déficit résiduel dû aux conflits d’injectivité). Cette seconde quantité mesure le résidu après retrait des symboles de degré nul; elle ne prétend pas identifier un unique sous-ensemble de Hall témoin.

Le calcul reconstruit exactement les étiquettes 1ter : **7 200/7 200** cas individuels concordent pour C-moyenne et C-DCT, B∈{2,4,8}, 100 couvertures et 12 messages de 100 octets source. Les lignes agrégées `ALL12` et les répétitions JPEG/bruit ont été exclues du rapprochement individuel.

Pour C-moyenne à B=8, parmi les 224 messages infaisables sur 1 200 tentatives individuelles, le déficit médian est **13,5 symboles comprimés**, le 90e percentile 55,4, le 99e percentile 75 et le maximum 79. La médiane de `d/n` est **14,82 %**. H11 (médiane ≤3 symboles) n’est donc pas soutenue pour cette configuration. Le déficit typique dépasse quelques symboles; l’affectation partielle reste à évaluer, sans être présumée suffisante.

## D1 — déficits des messages infaisables

Les quantiles portent sur les messages infaisables; `d/n` est calculé message par message avant de prendre la médiane.

| Descripteur | B | Infaisables / 1 200 | Médiane d | Q90 d | Q99 d | Max d | Médiane d/n | Moyenne d_vide | Moyenne d_Hall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C-moyenne | 2 | 616 | 7 | 52 | 85,85 | 95 | 9,26 % | 9,10 | 8,61 |
| C-moyenne | 4 | 376 | 10 | 54,5 | 83 | 90 | 13,89 % | 6,96 | 12,58 |
| C-moyenne | 8 | 224 | 13,5 | 55,4 | 75 | 79 | 14,82 % | 4,39 | 17,02 |
| C-DCT | 2 | 863 | 10 | 68 | 97,38 | 104 | 16,67 % | 13,60 | 10,34 |
| C-DCT | 4 | 587 | 15 | 71 | 97,56 | 103 | 18,52 % | 10,72 | 15,05 |
| C-DCT | 8 | 393 | 19 | 72 | 100 | 101 | 22,52 % | 8,12 | 19,39 |

Pour C-moyenne, B=8, la somme des déficits moyens se décompose en 4,39 symboles à candidat vide et 17,02 symboles de déficit résiduel par message infaisable. Parmi ces 224 échecs, 109 comportent au moins un symbole sans candidat; 216 ont un déficit résiduel `d_Hall>0`; 8 ont `d_Hall=0`, c’est-à-dire que tout leur déficit s’explique par des symboles isolés. Les deux causes coexistent dans de nombreux messages.

## D2 — concentration des octets sans candidat

À C-moyenne, L=12, B=8, sur les 100 couvertures D, il y a en moyenne **2,58 valeurs cibles sur 256 sans position robuste**, avec médiane 0, Q90=3 et maximum 91. **13 couvertures sur 100** ont au moins un tel trou; 87 n’en ont aucun. Les trous sont donc concentrés sur une minorité de couvertures, avec un cas extrême, plutôt que répartis uniformément.

La moyenne de 2,58 provient de 258 paires couverture/valeur sans candidat sur 25 600. Le taux agrégé de 1,01 % ne signifie donc pas qu’environ 2,6 valeurs soient absentes dans chaque couverture. Pour les messages effectivement testés à B=8, 109 des 224 cas infaisables C-moyenne contiennent au moins un symbole sans candidat. Toutefois, seuls 8 de ces déficits sont entièrement expliqués par ce phénomène; le déficit résiduel de couplage concerne 216 cas.

## D3 — faisabilité individuelle et intervalles

Les taux individuels et les IC bootstrap par grappes de couvertures (10 000 réplications, graine 20261119) sont dans `per_message_feasibility_bootstrap.csv`. Pour C-moyenne, B=8, les estimations ponctuelles vont de 72 à 95 %; aucune des 12 n’atteint 100 %. C-DCT va de 52 à 87 %. Ces taux individuels ne changent pas le critère conjoint 1ter : 68/100 couvertures C-moyenne et 47/100 C-DCT satisfont simultanément les 12 messages.

## D4 et D5 — cohérence et coût fixe

- Le contrôle G-T0 déjà archivé reproduit les 4 480 observations de contrôle avec un écart de 0,00 point. Le présent calcul ajoute l’accord exact 7 200/7 200 entre couplage maximal reconstruit et étiquettes individuelles de 1ter.
- À B=8 et L=12, le coût fixe reste de 16 bits par symbole pour BOWS2 256×256 (11 bits de jeton + 5 bits de résidu) et 18 bits pour BOSSBase 512×512 (13+5). Cette dernière valeur est une formule de capacité; aucune mesure de déficit BOSSBase n’a été faite ici.

## Lecture de G-Q0 et limites

Pour le descripteur exploratoire C-moyenne à B=8, la médiane du déficit représente 14,82 % de la longueur comprimée : cela tombe dans la zone 10–25 % de la barrière G-Q0, si l’on applique cette barrière telle qu’écrite. La section 2 du brouillon dit cependant d’abandonner A2 au-delà de 10 %, tandis que la section 9 autorise A2 avec p≥30 % dans la zone 10–25 %. Le brouillon ne permet donc pas de prendre une décision cohérente sur la poursuite d’A2 avant correction et gel.

Ce diagnostic ne mesure ni Reed–Solomon, ni le remplissage non robuste, ni le choix de couverture, ni la transmission géométrique. Le déficit décrit une affectation partielle sur les positions robustes telles que définies par le criblage 1ter (K=50 pour les descripteurs de remplacement). Il ne prouve pas que le code correcteur récupérera les symboles manquants après perturbation.
