# D6 et D7 — diagnostics post hoc sur les sorties 1ter

**Date :** 18 novembre 2026
**Statut :** calculs descriptifs sur les 100 couvertures D déjà ouvertes; pas de nouvelle lecture d’image ni de perturbation.
**Jeu de positions :** C-moyenne, L=12, robustesse archivée en 1ter avec K=50 JPEG + K=50 bruit.
**Script :** `scripts/audit_step1quater_d6_d7.py`.

## D6 — déficit du mot codé

### Calcul

Les 12 messages de 100 octets source sont comprimés avec zlib-9, comme en 1ter. Pour chaque message et p∈{0,10,20,30,40 %}, la parité est arrondie par excès sur Lc et ajoutée au message; le couplage maximal est recalculé avec les positions robustes enregistrées, pour B=4 et B=8. À cette longueur source, les mots comprimés tiennent chacun dans un seul bloc de 128 octets.

Deux parités sont comparées :

1. **RS exact :** `reedsolo` 1.7.0, GF(256), `prim=0x11d`, générateur 2, `fcr=0`, avec le nombre exact de symboles de parité prévu.
2. **Proxy aléatoire :** octets de parité pseudo-aléatoires déterministes, graine de base 20261120, une séquence par famille/message/p. Cette ligne reproduit le proxy du protocole; elle ne borne pas le comportement d’un code RS réel.

Pour un mot RS précis, `d≤P` est une condition nécessaire pour que tous les symboles non placés puissent être corrigés comme effacements sur un canal parfait. La fraction correspondante borne alors le succès potentiel de l’affectation partielle **sur ces couvertures D et ces mots précis**; elle ne tient pas compte des erreurs de transmission, du CRC ni d’autres défaillances. Le proxy aléatoire n’a pas cette interprétation de borne.

### Résultat global sur les 12 messages

Fraction des 1 200 cas couverture/message pour lesquels le déficit maximal d ne dépasse pas la parité P :

| Parité | B=4, RS exact | B=8, RS exact | B=4, proxy aléatoire | B=8, proxy aléatoire |
|---:|---:|---:|---:|---:|
| 0 % | 68,7 % | 81,3 % | 68,7 % | 81,3 % |
| 10 % | 82,1 % | 87,3 % | 82,3 % | 88,1 % |
| 20 % | 85,8 % | 90,2 % | 85,6 % | 89,8 % |
| 30 % | 87,5 % | 92,1 % | 88,0 % | 92,2 % |
| 40 % | 89,2 % | 92,5 % | 89,7 % | 92,9 % |

À B=8 et p=40 %, la condition nécessaire est satisfaite dans 92,5 % des cas RS exacts sur D-a, sous le seuil de succès de 95 % de G-Q2, même avant erreurs de canal. Par famille, cette fraction est 98,7 % pour les messages répétés, 91,3 % pour le texte naturel, 89,3 % pour l’ASCII et 90,7 % pour les octets uniformes. La moyenne sur les 12 messages masque donc des écarts de famille substantiels.

Cela rend **A2 seul peu prometteur sur D-a**, mais ne constitue pas un résultat confirmatoire sur le jeu D-b réservé au développement. Les combinaisons avec A3/A4 ne sont pas couvertes par cette borne D6. Aucun code correcteur n’a été évalué sous JPEG ou bruit ici.

À p=40 %, le coût `b_assign` moyen sur les 12 messages reste sous 24 bits/octet source en raison des familles très compressibles : Lcw moyen = 113,08; à B=8, `b_assign=113,08×17/100=19,22`. Pour les seuls messages uniformes de 100 octets, Lc=111, P=45, Lcw=156 et `b_assign=26,52`; l’ASCII est également au-dessus de 24 en moyenne de famille (25,84). Il faut donc conserver l’agrégat prévu par le protocole et présenter les familles séparément.

## D7 — distribution des hachages robustes et fenêtres saturées

Les distributions robustes de C-moyenne sont plus concentrées que celles de l’ensemble des positions :

| Pool de positions (100 couvertures) | Entropie moyenne | Support effectif moyen 2ᴴ | Valeurs distinctes, médiane | Masse dans les 10 valeurs les plus fréquentes, médiane |
|---|---:|---:|---:|---:|
| Toutes les positions | 7,395 bits | 171,8 | 248 | 17,1 % |
| Positions robustes | 6,760 bits | 119,9 | 178 | 21,8 % |

La sélection de robustesse est donc associée à une concentration mesurable des hachages. Ce résultat est compatible avec l’hypothèse « stable mais moins diverse », mais ne démontre pas à lui seul que cette concentration cause les déficits de Hall.

Pour chaque message et valeur cible x, une fenêtre ±B est déclarée saturée si le nombre demandé du byte x dépasse le nombre de positions robustes dont le hachage est dans [x−B,x+B]. C’est un témoin de Hall sur une valeur seule. À B=8, sur les 224 cas infaisables C-moyenne :

- 142 présentent au moins une valeur cible dont la fenêtre est saturée;
- 134 ont à la fois une fenêtre saturée et un résidu de Hall `d_Hall>0`;
- 82 ont `d_Hall>0` sans aucune fenêtre saturée pour une valeur prise isolément;
- 8 n’ont pas de résidu Hall, et leur déficit provient entièrement de symboles sans candidat.

Les fenêtres d’un seul byte expliquent donc une partie des échecs, mais pas les 82 résidus qui ne présentent aucune surcharge marginale par valeur. Ceux-ci proviennent de la compétition entre plusieurs valeurs dont les voisinages ±B se recouvrent. Il faudrait une analyse de sous-ensembles/intervalles si l’on veut attribuer ces cas à des témoins de Hall précis.

## Portée

D6/D7 utilisent le jeu exploratoire D-a et les positions robustes choisies dans 1ter. Ils servent à juger l’intérêt pratique de la grille, pas à confirmer une solution. Ils n’évaluent ni A2/A3/A4 sur D-b, ni les résultats sur E/C/F, ni la sécurité ou la synchronisation géométrique. Aucune conclusion de l’article ne doit être modifiée sur la base de ces diagnostics avant le gel et la validation prévus.
