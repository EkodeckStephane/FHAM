# Revue du brouillon de protocole 1quater

**État :** revue préparatoire; le protocole fourni dans Downloads n’a pas été modifié ni gelé. Le diagnostic G-Q0 est exécuté sur les sorties déjà ouvertes de 1ter et reste explicitement post hoc. Aucune mesure A1–A5 n’a été lancée.

## Corrections nécessaires avant gel

1. **Règle contradictoire pour A2 (bloquant).** La section 2 abandonne A2 si le déficit médian dépasse 10 % de n; la section 9 classe 10–25 % en orange et poursuit A2 avec p≥30 %. G-Q0 donne, pour C-moyenne B=8, une médiane d/n de 14,82 % : ces deux règles conduisent à des décisions opposées. Choisir une seule règle avant le gel. Le tableau G-Q0 est descriptif et n’autorise pas à sélectionner après coup la branche favorable.
2. **Définition de n et ordre compression/codage (bloquant).** 1ter affecte les octets après zlib-9; le brouillon appelle n la longueur source et calcule par ailleurs le coût RS en fonction de n. Définir séparément la longueur source, la longueur comprimée, les octets de CRC éventuels et la longueur du mot codé. Définir si p est un pourcentage des octets source ou des octets comprimés et comment l’arrondi est appliqué.
3. **Longueur maximale Reed–Solomon GF(256) (bloquant pour 200 octets).** Le mot RS standard sur GF(256) a au plus 255 symboles. Dans les fichiers actuels, les messages uniformes de 200 octets font 211 octets après zlib-9; avec 30 % de parité, cela ferait 275 symboles. Le protocole doit spécifier le découpage en blocs RS, la taille de chaque bloc, les parités par bloc et le traitement du dernier bloc. Sinon A1/A2 à 200 octets n’est pas défini.
4. **G-Q1 ambigu.** La courbe est demandée « par message », mais n* est défini au singulier. Définir n* séparément pour chacun des 12 messages et pour la faisabilité conjointe des 12, puis préciser laquelle détermine la porte. Garder aussi la longueur source et la longueur comprimée dans les sorties.
5. **Robustesse K incohérente avec 1ter.** Le criblage C-moyenne/C-DCT de 1ter utilise K=50 JPEG et K=50 bruit (provenance archivée); K=100 s’applique à l’analyse spectrale antérieure. Pour le G-Q0 post hoc, les positions déjà calculées doivent rester inchangées. Pour D-b, déclarer K=100 comme un nouveau choix du protocole, et définir exactement la règle de robustesse et l’estimation de stabilité utilisée pour classer les positions non robustes.
6. **Messages de 25 octets absents.** Le dépôt contient actuellement les fichiers 10, 50, 100 et 200 octets pour les quatre familles, mais pas 25. Définir avant le gel leur génération déterministe. Pour une courbe imbriquée, on peut préenregistrer les 25 premiers octets des mêmes fichiers de 50 octets, avec un contrôle SHA-256; sinon produire et geler de nouveaux messages et leurs graines.
7. **Combinaison des leviers et règle de sélection.** Les étapes A2, A3 et A4 sont successives, mais le protocole ne dit pas clairement si elles sont testées isolément ou composées. Définir les configurations admissibles (A2 seul, A3 seul, A4 seul, combinaisons autorisées), les dépendances entre elles et la procédure d’optimisation avant D-b. Inclure p, q, m et B dans la table de toutes les cellules réellement testées.
8. **Coût de communication incomplet pour A4 et G-Q2.** La formule b_source couvre le coût fixe d’affectation et le bitmap, mais pas le nonce/tag AES-GCM, le cadrage du record, l’identifiant de couverture, ni le nombre d’images envoyé lorsque le message est découpé. Déclarer si une galerie est prépartagée; rapporter à la fois le coût de la couche d’affectation et le coût réel du record/communication, avec les identifiants et arrondis. La porte 24 bits/octets doit préciser laquelle de ces métriques elle borne.
9. **Validation E et choix de N.** Le calcul de N utilise un pilote de 20 couvertures tiré de E, alors qu’E est ensuite présenté comme validation à passage unique. Séparer explicitement le pilote du jeu confirmatoire E, ou estimer N sur D-b; ne pas réutiliser des observations E qui ont influencé le choix de configuration dans la validation finale.
10. **Sécurité et revendications.** Le protocole exclut la sécurité de bout en bout et la détectabilité. Il peut évaluer les effets capacité/RS, mais ne pourra pas lever à lui seul les critiques Reviewer 2 sur la chaîne de communication, l’association image–métadonnées, le rejeu et l’établissement de clés. Séparer ces conclusions dans l’article et dans la lettre de réponse.

## Diagnostic G-Q0 déjà réalisé

- 7 200 cas individuels reconstruits à partir des positions robustes et des messages fixés; accord exact avec les étiquettes de faisabilité 1ter : 7 200/7 200.
- Pour C-moyenne à B=8 : 224/1 200 messages infaisables; déficit médian 13,5 symboles comprimés; médiane d/n=14,82 %; moyenne `d_vide=4,39` et `d_Hall=17,02` par cas infaisable.
- Les seuils contradictoires de G-Q0 s’appliqueraient précisément à ce résultat; corriger cette contradiction avant tout gel.
- Sur C-moyenne B=8, 13/100 couvertures ont au moins un octet cible sans candidat robuste; médiane 0, Q90=3, maximum 91. Parmi les messages infaisables, 109/224 contiennent au moins un symbole sans candidat, tandis que 216/224 ont aussi un déficit résiduel de couplage.
- Le détail, les IC bootstrap par message, le script et les limites sont dans `results/stability_step1/step1ter/audit_diagnostics/GQ0_posthoc/`.

## Statut des jeux

La provenance 1ter liste 100 couvertures D pour le criblage/plafond; le manifeste gelé contient 200 couvertures D. Les 100 restantes sont donc candidates à D-b. Avant le gel, il faut confirmer leur absence de tout calcul de pixel dans les autres journaux/scripts 1ter et figer leur liste exacte par SHA-256. E, C et F restent fermés.

## Décision

G-Q0 est exploitable comme diagnostic descriptif post hoc. Il n’autorise pas à conclure que Reed–Solomon réussira : à C-moyenne B=8, le déficit comprend une composante Hall plus importante que la composante de symboles isolés, et le canal ajoute encore erreurs et dépendances. A2 mérite d’être évalué seulement après clarification de ses seuils, de la longueur RS et du budget de bits. Aucune étape A1–A5 ne doit commencer avant correction et gel du protocole, puis autorisation de lancement.
