# Relecture avant gel du protocole 1quater

**Date : 20 novembre 2026.** Relecture des sections 2, 4, 6 et 9 du protocole fourni (version (2)), corrections intégrées à `FHAM_etape_1quater_preregistre.md`. Aucun calcul A1–A5 n'a été exécuté.

## Section 2 — diagnostics et résultats post hoc

- D6 et D7 sont présentés comme déjà exécutés sur D-a, avec les valeurs vérifiées du rapport : 92,5 % à B=8/p=40 pour les mots RS exacts ; entropie 6,760 bits ; décomposition 142/224 et 82/224.
- La phrase qui jugeait D6 sur un mot non codé a été retirée. La grille de D-b demeure intégrale ; les résultats D-a restent exploratoires.
- La longueur comprimée est notée L_c, le mot codé L_cw et la longueur source L_src ; le déficit est défini sur le mot effectivement affecté.

## Section 4 — facteurs et coûts

- Les blocs RS sont définis sur GF(256), de longueur source maximale 128, avec P_b=ceil(p·l_b). La condition de décodage utilise P_b et non le taux p : e+2t≤P_b.
- A1 est indexé en octets source L_src ; A3 plafonne la sélection non robuste sur L_cw (ou n sans code). `b_assign` distingue les symboles effectivement placés du bitmap complet.
- La règle de coût b_total évite le double comptage : b_total=8(F+Z_9)/L_src. L'enveloppe FHAM ajoute F=41 octets fixes ; le format direct ajoute 29. L'en-tête interne de 15 octets est dans le plaintext compressé.
- Le corps 1quater est maintenant spécifié champ par champ : identifiant de configuration, longueurs source/comprimée/codée, CRC, annuaire des segments et couvertures, bitmap et enregistrements des positions. Les IDs de configuration et le traitement des segments A4 sont déterministes.
- Limite d'implémentation consignée : le sérialiseur actuel accepte un objet `Assignment` seulement. Il ne produit pas encore le corps 1quater avec CRC, bitmap et identifiants de galerie. Z_9 et b_total ne seront donc pas revendiqués avant l'implémentation et la mesure byte-for-byte de ce corps.

## Section 9 — barrières

- G-Q1 définit L_src* et rapporte distinctement les 12 messages et l'événement conjoint ; aucun seuil d'acceptation additionnel n'est introduit.
- Les intervalles G-Q2 sont disjoints : vert si succès≥0,95 et b_assign≤24 ; orange si succès∈[0,90;0,95[ ou b_assign∈]24;28] ; rouge si succès<0,90 ou b_assign>28.
- E, C et F restent fermés jusqu'aux barrières indiquées. Le test présent vérifie seulement l'identité hash des entrées ; aucun pixel D-b n'a été ouvert.

## Gel des entrées et mesure préalable

- D-a : 100 images tirées de la provenance 1ter. D-b : les 100 autres entrées du split D, excluant les identifiants et hashes de D-a ; aucune sortie 1ter nommée par les identifiants D-b n'a été trouvée.
- Messages : 48 artefacts tracés (4 familles × 3 indices × 4 longueurs). Les 12 fichiers de 25 octets sont les préfixes byte-for-byte des fichiers de 50 octets correspondants.
- Reed–Solomon : `reedsolo==1.7.0`; versions runtime et graines consignées dans le manifeste.
- Mesure du sérialiseur courant : en-tête interne 15 octets, zlib-9 de l'en-tête vide 21 octets, enveloppe FHAM vide 62 octets, dont F=41 ; enveloppe directe vide 29 octets, dont F=29.

Les empreintes et la procédure reproductible sont dans `results/stability_step1/step1quater/manifest/`; `scripts/freeze_step1quater_inputs.py` refait ces contrôles sans lancer la grille.

## Conditions préalables encore ouvertes avant A1–A5

1. Exécuter le sérialiseur du corps 1quater décrit à la section 6, figer son implémentation, puis mesurer Z_9 et b_total. Cette étape est obligatoire avant de rapporter le coût complet ; elle ne change pas F=41 déjà mesuré.
2. Établir la correspondance entre les 100 identifiants `.pgm` D-b gelés et les images effectivement disponibles. `D:\dataset` est accessible, mais contient les archives PCAP du jeu ISCX ; le corpus Baleba fourni contient 400 PNG BOWS2 en niveaux de gris, 256 × 256, sous noms hashés. Aucun manifeste de correspondance vers les identifiants source `.pgm` n'a été trouvé. Aucune comparaison de pixels n'a été faite et aucun fichier de ce corpus dérivé n'a été substitué au split D-b.
3. Implémenter puis vérifier le sérialiseur 1quater avant de mesurer Z_9 ou b_total. Le gel de la liste des entrées est commité ; la grille A1–A5 n'est pas lancée.

Les critiques de sécurité de la chaîne complète, la synchronisation géométrique et le coût de distribution de la galerie A4 restent hors périmètre de ce protocole et doivent demeurer explicitement qualifiés dans l'article et la réponse aux reviewers.
