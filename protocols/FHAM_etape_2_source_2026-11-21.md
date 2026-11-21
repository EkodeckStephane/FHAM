# FHAM — Protocole de l'étape 2 : sécurité de bout en bout, détectabilité réseau et synchronisation géométrique

Nov 21, 2026 · @Ekodeck Stéphane

## 1. Objectif, point de départ et questions

L'étape 2 précise, par spécification et par mesure, ce que FHAM établit sur trois fronts laissés hors périmètre par 1quater : la sécurité de bout en bout, la détectabilité réseau et la synchronisation géométrique. Chaque piste a une sortie bornée ; aucune ne promet une garantie générale.

**Statut du document (21 novembre 2026).** Brouillon, à geler et à commiter avant toute mesure. Les résultats de 1quater sont en lecture seule. La piste S fixe le format réellement transmis ; les pistes D et G s'y appuient.

### Point de départ (1quater)

| Grandeur | Valeur |
| --- | --- |
| Configuration figée | p = 10 %, q = 5 %, m = 2, B = 4, descripteur C-moyenne, L = 12 |
| Succès JPEG 75 / bruit σ = 2 | E : 97,04 / 97,46 % ; C : 94,71 / 94,00 % ; F : 98,75 / 98,21 % |
| Record complet, 100 octets | environ 327 octets sur C et 340 sur F, contre 129 pour AES-GCM direct |
| Coût par famille de messages | de 10,18 à 33,08 bits par octet source sur C (10,37 à 34,59 sur F) |
| Sécurité évaluée en 1quater | aucune |
| Sécurité évaluée dans l'article | profil de session (liaison à la couverture, rejeu, offre signée altérée) testé 40/40 ; compromission de la clé d'identité non évaluée |
| Géométrie | exact 0/40 après recalage ; perte de 14 à 45 points entre décodage sans recalage et inverse oracle (étape 1) |

Deux faits de 1quater changent la question de sécurité. Le record porte maintenant une galerie de deux couvertures, une parité, un bitmap d'effacement et un CRC, que le profil testé dans l'article ne couvrait pas. Et la taille du record varie avec la compressibilité du message, donc peut en révéler le type.

### Questions

- **S1.** Le format de 1quater conserve-t-il les propriétés testées dans l'article (liaison à la couverture, rejeu, falsification) ?
- **S2.** Que doivent lier les données associées lorsque l'émetteur choisit parmi m = 2 couvertures ?
- **S3.** Quelle propriété vise-t-on après compromission d'une clé à long terme, et comment la tester ?
- **D1.** La longueur du record révèle-t-elle la famille du message, et une représentation à taille fixe supprime-t-elle cette fuite, à quel coût en bits ?
- **D2.** Un classifieur distingue-t-il des flux FHAM de flux de référence au-dessus du hasard, avec la représentation compacte puis avec la représentation à taille fixe ?
- **G1.** Une recherche de transformation validée par le CRC ou l'étiquette AEAD retrouve-t-elle le message sous rotation, échelle et recadrage bornés ?
- **G2.** Quels sont le coût de calcul et le taux de faux accept de cette recherche ?

### Hypothèses

- **HS1.** Une fois la galerie liée aux données associées, le format de 1quater rejette toutes les falsifications et tous les rejeux testés (le résultat de l'article, 40/40, porte sur peu d'essais).
- **HD1.** La longueur du record compact permet de prédire la famille du message avec une exactitude supérieure à 25 %, le hasard pour quatre familles équilibrées.
- **HD2.** Une représentation à taille fixe ramène cette exactitude à 25 % près, au prix d'un surcoût à mesurer.
- **HG1.** La recherche validée par CRC retrouve le message dans une plage bornée de transformations, avec un taux de faux accept négligeable devant l'échelle des mesures.

### Hors périmètre

Preuve formelle complète de sécurité ; protocole TLS réel ; adversaire actif sur le canal de distribution de la galerie ; sténanalyse de contenu pixel (la couverture n'est pas modifiée) ; transformations géométriques fortes ; descripteurs invariants à la géométrie ; réponse aux reviewers, qui suit la révision du manuscrit.

## 2. Périmètre, format figé et modèles d'adversaire

Le format de record de 1quater est le point de départ de la piste S ; il est figé avant toute mesure, sauf les variantes listées à la section 3.

### Format figé (1quater)

| Champ | Contenu | Authentifié par |
| --- | --- | --- |
| Enveloppe publique | en-tête de format, nonce de 12 octets, étiquette de 16 octets (article, § 5.16) ; taille de l'en-tête non précisée, à mesurer sur le sérialiseur réel | — |
| Contenu chiffré | CRC-32 (4 octets), longueur (2 octets), indice de galerie (1 bit pour m = 2), bitmap d'effacement (L\_cw bits), jetons et résidus | étiquette AEAD |
| Données associées | digest de la couverture, identifiant de session, numéro de séquence (profil de l'article) | étiquette AEAD |

La galerie de m couvertures est prépartagée, comme la couverture unique de FHAM. Les clés d'identité sont provisionnées, comme dans l'article.

### Adversaires

| Adversaire | Capacité | Piste |
| --- | --- | --- |
| A1, passif sur le réseau | observe les flux, veut détecter FHAM ou inférer le type de message | D |
| A2, actif sur le réseau | modifie, rejoue, réordonne le record ; substitue une couverture ou la galerie ; modifie l'offre de clé | S |
| A3, compromission ultérieure | enregistre le trafic, obtient plus tard une clé d'identité | S |
| A4, canal image | transformations accidentelles non adverses : JPEG, bruit, géométrie | G |

L'adversaire est supposé connaître toutes les couvertures de la galerie, cas le plus défavorable : la confidentialité repose sur l'AEAD du record, non sur le secret de l'image. Un adversaire géométrique qui choisit la transformation pour détruire le message est hors périmètre ; la piste G étudie des transformations accidentelles de plage bornée.

### Ce qui est mesuré, argumenté, exclu

| Sujet | Nature de la preuve |
| --- | --- |
| Rejet des falsifications et rejeux | mesure sur le code, avec bornes de la règle de trois |
| Secret après compromission de clé | test de non-déchiffrement et argument de conception (secret phémère) |
| Authentification du handshake | argument symbolique facultatif, avec ses limites énoncées |
| Longueur et classifieurs | mesure sur des corpus déclarés ; « non détecté par ces classifieurs », jamais « indétectable » |
| Recherche de transformation | mesure sur des plages bornées |
| Preuve formelle complète, TLS réel | exclus |

## 3. Piste S : sécurité de bout en bout

La piste S spécifie les données associées du nouveau format, teste le rejet des falsifications et des rejeux sur ce format, puis évalue le secret après compromission de clé.

### S-1. Données associées

Le profil de l'article lie le digest d'une couverture unique, l'identifiant de session et le numéro de séquence. Avec m = 2, il faut aussi lier la galerie et les paramètres du format, pour qu'on ne puisse ni substituer une couverture, ni réordonner la paire, ni rétrograder les paramètres.

| Variante | Données associées |
| --- | --- |
| V0, article | digest de la couverture, session, séquence |
| V1, proposée | V0 plus digest ordonné des m couvertures de la galerie, version du format, m, p, B, profil L, identifiant du descripteur |

L'indice de la couverture choisie reste dans le contenu chiffré ; le récepteur vérifie que la couverture utilisée pour le décodage porte le digest de la galerie à cet indice.

### S-2. Intégrité du message reconstruit

Le message est reconstruit à partir des hachages de l'image, que l'étiquette AEAD ne couvre pas. Il est protégé par un contrôle placé dans le contenu chiffré.

| Variante | Contrôle | Coût |
| --- | --- | --- |
| I0 | CRC-32 des L\_c octets comprimés | 4 octets |
| I1 | digest SHA-256 tronqué à 128 bits des L\_c octets | 16 octets |

Un adversaire qui modifie des pixels ne connaît pas les positions utilisées (elles sont dans le record chiffré) ni le contrôle attendu. Une modification aléatoire est détectée avec une probabilité de 1 − 2⁻³² avec I0. Un oracle d'acceptation en ligne permettrait environ 2³² essais pour forcer un CRC ; la mesure le chiffre et compare I0 à I1.

### S-3. Falsification et rejeu

Chaque classe est testée sur le format V1 avec 1 000 essais aléatoires, en plus d'un balayage exhaustif de tous les basculements d'un bit sur 20 records d'environ 327 octets, soit environ 52 000 essais.

| Classe de mutation | Rejet attendu |
| --- | --- |
| bit retourné dans l'en-tête, le nonce, le chiffré ou l'étiquette ; troncature ; extension | étiquette AEAD |
| rejeu du même record, y compris après réouverture de la base de rejeu | garde de rejeu |
| séquence réordonnée ou sautée | garde de rejeu |
| couverture remplacée par l'autre de la galerie, ou par une image hors galerie | liaison de la couverture |
| galerie réordonnée ou substituée | données associées V1 |
| m, p, B, profil ou descripteur modifiés (rétrogradation) | données associées V1 |
| record d'une autre session recollé | identifiant de session |
| offre de clé signée altérée | signature |

Une mutation acceptée est une défaillance. Zéro acceptation sur 1 000 essais borne le taux à 3 × 10⁻³ (règle de trois, 95 %) ; zéro sur 52 000 le borne à environ 6 × 10⁻⁵. La variante V0 est rejouée sur les mêmes classes pour montrer ce que V1 ajoute.

### S-4. Compromission de clé

- **Secret rétrospectif.** Après une session, enregistrer le trafic, publier les clés d'identité privées et tenter de déchiffrer sans les clés éphémères. L'attendu est un échec, et la suppression des clés éphémères en fin de session est vérifiée dans le code.
- **Indépendance des sessions.** Une clé de session divulguée ne doit pas déchiffrer une autre session (contextes HKDF distincts).
- **Usurpation après fuite.** La fuite de la clé d'identité de A permet d'usurper A, ce qui est attendu ; elle ne doit pas permettre d'usurper B auprès de A (compromission de clé avec usurpation de pair). Scénario scripté, documenté.
- **Perte de la base de rejeu.** Effet d'une base de rejeu vide ou restaurée, documenté et atténué par un compteur d'époque lié à la session.

### S-5. Modèle symbolique (facultatif)

Un modèle symbolique du handshake (par exemple ProVerif) peut établir l'authentification mutuelle, le secret de la clé de session et la liaison à la galerie sous primitives idéales. Il ne remplace pas les tests ; ses hypothèses (primitives idéales, pas de défaut d'implémentation) sont énoncées dans le rapport. Non fait, il est listé comme limite.

## 4. Piste D : détectabilité réseau

La couverture n'est pas modifiée : une sténanalyse de pixels n'a pas d'objet. Ce qu'un observateur voit est le record, de longueur variable, la poignée de main de session et le volume du flux. La piste D mesure ce que ces observables révèlent.

### D-1. Fuite de longueur

En 1quater, le coût total varie de 10,18 à 33,08 bits par octet source selon la famille (corpus C). Si le record compact conserve cette variation, sa longueur révèle la compressibilité du message.

- **Messages.** Quatre familles × 100 messages de 100 octets sources, générés avec une graine figée et disjoints des 12 messages de 1quater. Avec 12 messages, la longueur identifierait simplement le message.
- **Mesure.** Exactitude d'un classifieur à quatre classes qui n'utilise que la longueur du record, validation croisée groupée par message ; information mutuelle empirique entre longueur et famille.
- **Hasard.** 25 % pour quatre familles équilibrées. HD1 est confirmée si l'IC à 95 % de l'exactitude exclut 25 %.

### D-2. Représentations comparées

| Représentation | Définition |
| --- | --- |
| R0, compacte | record de 1quater, longueur variable |
| R1, à taille fixe | record complété par du remplissage chiffré jusqu'à une classe publique de capacité ; pour 100 octets sources, une seule classe de 128 symboles |

Le remplissage a un coût : à B = 4 et M = 1 764, 16 bits par symbole (11 de jeton, 4 de résidu, 1 de bitmap), donc 128 × 16 / 100 = 20,48 bits par octet source pour la couche d'affectation, contre 14,12 en moyenne en 1quater, soit environ 45 % de plus. C'est une estimation ; la mesure porte sur le record complet.

### D-3. Classifieurs sur flux

- **Flux de référence.** Le corpus de trafic TLS non-VPN de l'article (taille et provenance à confirmer et à figer par SHA-256).
- **Flux FHAM.** Générés en exécutant l'émetteur et le récepteur réels sur un réseau local, capturés en pcap, pour les représentations R0 et R1, avec un transport TCP direct puis un transport sous TLS 1.3. Les offres de clé signées (208 octets par session selon l'article) sont incluses.
- **Caractéristiques.** Tailles et sens des dix premiers paquets, volume total, nombre de paquets, délais entre paquets, durée.
- **Modèles.** Régression logistique, forêt aléatoire et gradient boosting ; référence triviale fondée sur le seul volume total.
- **Séparation.** Apprentissage et test séparés par session ; le test n'est vu qu'une fois par modèle figé.
- **Échelle.** 1 000 flux par classe ; à AUC = 0,5, la demi-largeur de l'IC à 95 % vaut environ 0,025 (approximation de Hanley–McNeil).

### D-4. Empreinte de la poignée de main

Deux offres signées de taille constante forment une empreinte si elles sont visibles. Mesurer si les classifieurs de D-3 les exploitent, avec et sans leur intégration dans la charge utile chiffrée du premier record.

**Limite.** Un résultat proche de 0,5 signifie « non détecté par ces modèles, sur ce corpus ». Il n'établit pas l'indétectabilité contre un adversaire qui entraînerait un classifieur spécialisé sur R1.

## 5. Piste G : synchronisation géométrique

Deux obstacles se cumulent : estimer la transformation, puis lire des hachages stables après rééchantillonnage. L'étape 1 a mesuré une perte de 14 à 45 points même avec l'inverse oracle, ce qui montre que le second obstacle existe déjà quand la transformation est connue. La piste G mesure d'abord la largeur du bassin de réussite autour de la bonne transformation, puis évalue une recherche validée par le contrôle d'intégrité.

### G-0. Hypothèse de référence à confirmer

Le protocole distingue deux régimes selon que le récepteur dispose ou non d'une référence non transformée (la galerie prépartagée) pour estimer la transformation par ORB/RANSAC, comme P2 de l'étape 1.

| Régime | Source des candidats |
| --- | --- |
| G-ref | estimation ORB/RANSAC, puis candidats voisins |
| G-aveugle | grille bornée autour de l'identité, sans référence |

Le régime effectivement applicable à FHAM est à confirmer sur le code et sur le modèle de transmission ; les deux sont mesurés tant que ce n'est pas fait.

### G-1. Transformations et plages

Les valeurs reprennent la structure de l'étape 1ter : développement aléatoire avec trous, validation fixe, jeu scellé plus sévère.

| Famille | Développement | Validation | Jeu scellé |
| --- | --- | --- | --- |
| Rotation | U\[−2° ; +2°\], hors \[0,9° ; 1,1°\] et \[−1,4° ; −1,1°\] | +1° | −1,25° |
| Recadrage-restauration | U\[2 % ; 8 %\], hors \[4,5 % ; 5,5 %\] | 5 % | 9 % |
| Réduction-restauration | facteur U\[0,82 ; 0,95\] | ×0,8 | ×0,75 |

Interpolation tirée entre bilinéaire et bicubique en développement ; bicubique en validation et sur le jeu scellé.

### G-2. Bassin de réussite

Avec la bonne transformation connue à une erreur contrôlée près, mesurer le succès exact en fonction de l'erreur d'angle, d'échelle et de décalage, à la configuration figée de 1quater. La largeur du bassin donne le pas de grille nécessaire. Cette mesure est faite sur D-b d'abord ; elle fixe la taille de la recherche avant d'en estimer le coût.

### G-3. Recherche validée

Le récepteur parcourt un ensemble de transformations candidates, décode avec chacune et retient celle dont le décodage vérifie le contrôle d'intégrité du contenu chiffré.

- **Domaine.** Rotation ± 2°, échelle 0,80 à 1,25, décalage ± 24 pixels à 256 × 256 (± 48 à 512 × 512), paramètres similarité à quatre degrés de liberté.
- **Score intermédiaire.** Le code Reed–Solomon fournit une cohérence : nombre d'erreurs corrigées, ou échec. Il ne donne un signal que dans le bassin de G-2 ; au-delà, la recherche est exhaustive sur la grille déduite de G-2.
- **Validation finale.** Le contrôle d'intégrité de S-2 ; seule une transformation qui le vérifie est acceptée.
- **Faux accept.** Avec I0 (CRC-32) et K candidats, la probabilité d'acceptation fausse par tentative est bornée par K × 2⁻³². À titre d'exemple de calcul, pour une grille de 54 043 candidats (rotation ± 2° par pas de 0,25°, échelle 0,90 à 1,10 par pas de 0,02, décalage ± 8 pixels par pas de 1 : 17 × 11 × 289), cela ferait environ 1,3 × 10⁻⁵ ; la grille réellement retenue est bornée par la section 9. Avec I1 (128 bits), la borne est négligeable. Le choix entre I0 et I1 dépend de ce calcul pour la grille retenue.

### G-4. Coût de calcul

Un décodage ne lit que les positions du record (quelques centaines), non tout le codebook ; le coût par candidat est donc inférieur à celui d'un codebook complet (0,43 s). Il est mesuré sur 5 couvertures avant tout calcul de budget, puis rapporté en temps par décodage. Le plafond de 60 secondes par décodage sur un cœur est un choix de conception qui borne la taille de la grille (section 9) ; ce n'est pas une barrière de décision.

**Limite.** La recherche ne traite que le premier obstacle. Si G-2 montre un bassin très étroit ou un plafond de récupération même à transformation exacte, la limite est dans l'instabilité des hachages au rééchantillonnage, pas dans l'estimation, et la piste G le documente comme tel.

## 6. Données, perturbations et jeux scellés

La piste S n'a pas besoin de nouveau jeu d'images ; la piste D a besoin de messages et de flux nouveaux ; la piste G a besoin de couvertures qu'aucune mesure antérieure n'a vues sous transformation géométrique.

| Piste | Jeu | Taille | Statut |
| --- | --- | --- | --- |
| S | records générés sur D-b avec les 12 messages de 1quater | 20 records pour le balayage exhaustif, plus 1 000 essais par classe de mutation | D-b déjà utilisé pour le développement de 1quater |
| D | D-msg : 4 familles × 100 messages de 100 octets sources | 800 messages | nouveaux, graine figée, disjoints des 12 de 1quater |
| D | flux FHAM | 1 000 par représentation et par transport | générés sur réseau local, soit 200 sessions de 5 records |
| D | flux de référence | 1 000 | corpus TLS non-VPN de l'article, à figer par SHA-256 |
| G | D-b | 100 | développement : bassin (G-2), choix de la grille |
| G | E-geo | 200 | validation, ouvert une fois après le gel |
| G | C-geo | 200 | phase finale BOWS2, scellé |
| G | F-geo | 200 | phase finale BOSSBase, scellé |

E-geo et C-geo sont tirés par SHA-256 parmi les images de BOWS2-C que 1quater n'a pas ouvertes (7 125 images allouées à C, 200 utilisées) ; F-geo est tiré parmi les images de BOSSBase hors des 400 candidats de l'étape 1 et hors de F de 1quater. La disponibilité de ces images est à confirmer dans les manifestes avant le gel. Les images de E, C et F de 1quater ont été ouvertes sous perturbations photométriques ; elles ne sont pas réutilisées ici comme jeux scellés.

**Règles.**

- Images natives, sans redimensionnement : 256 × 256 pour BOWS2, 512 × 512 pour BOSSBase ; aucun résultat n'est extrapolé d'un corpus à l'autre.
- Partition par SHA-256, manifestes avec `pixels_opened=false` jusqu'à l'étape qui les consomme.
- Messages de G : les 12 messages de 1quater (quatre familles × trois indices).
- Perturbations géométriques de la section 5 ; aucune perturbation photométrique n'est mélangée à la géométrie sauf la composition listée au jeu scellé (rotation puis JPEG 65), rapportée à part.
- Graines distinctes pour les tirages de perturbation, les messages, les mutations, la partition des flux et les modèles. Bibliothèques figées, dont scikit-learn pour D et la bibliothèque Reed–Solomon de 1quater (reedsolo 1.7.0).

## 7. Métriques

Chaque piste a une métrique primaire qui porte sa barrière ; les autres sont rapportées sans décider.

| Piste | Métrique | Définition | Rôle |
| --- | --- | --- | --- |
| S | Acceptations de mutations | nombre de mutations acceptées par classe, sur le nombre d'essais, avec borne supérieure | primaire |
| S | Mécanisme de rejet | étiquette AEAD, garde de rejeu, liaison de la couverture, données associées, signature | diagnostic |
| S | Secret rétrospectif | déchiffrement réussi ou non après fuite des clés d'identité | primaire |
| S | Surcoût | octets ajoutés par V1 contre V0 et par I1 contre I0 (12 octets) | rapporté |
| D | Exactitude longueur vers famille | exactitude à quatre classes, hasard à 25 % | primaire pour HD1 |
| D | AUC | aire sous la courbe ROC, flux FHAM contre référence, pour le meilleur modèle | primaire pour HD2 |
| D | TPR à 1 % de FPR | taux de détection à faux positifs fixés | secondaire |
| D | Surcoût de R1 | bits par octet source du record complet, et ratio face à AES-GCM avec zlib-9 | rapporté |
| G | Succès exact | message exact après la recherche, sur toutes les tentatives | primaire |
| G | Bassin | succès en fonction de l'erreur d'angle, d'échelle et de décalage | diagnostic de G-2 |
| G | Chaînes comparées | P1 (coordonnées fixes), P2 (ORB/RANSAC), P3 (inverse oracle), P4 (recherche validée) | secondaire |
| G | Coût | nombre de candidats, temps par décodage | rapporté |
| G | Faux accepts | acceptations d'un message faux, sur toutes les tentatives | contrôle |

Les pistes D et G s'appuient sur le format validé par la piste S : si S change le format, les mesures de D et de G sont refaites sur le nouveau format avant d'être rapportées.

## 8. Statistiques et taille d'échantillon

L'unité statistique dépend de la piste : l'essai pour S, la session pour D, la couverture pour G.

- **S.** Bornes de la règle de trois et intervalles de Clopper–Pearson ; aucun test d'hypothèse. Zéro acceptation sur 1 000 essais donne une borne supérieure de 0,3 % ; sur 52 000, environ 0,006 %.
- **D.** Bootstrap par sessions, 10 000 tirages, pour l'exactitude et l'AUC. Le meilleur modèle est choisi sur une partition de validation, puis évalué une seule fois sur la partition de test, pour éviter un maximum optimiste. Pour 1 000 flux par classe à AUC = 0,5, la demi-largeur de l'IC à 95 % est d'environ 0,025 (Hanley–McNeil, approximation).
- **G.** Bootstrap par couvertures, 10 000 tirages ; Wilson pour les taux. Comparaison appariée de la recherche contre l'absence de recherche par test de permutation à inversion de signe (100 000 tirages, p = (1 + k) / 100 001), avec correction de Holm sur les trois familles de transformations.
- **Tailles de G.** D-b : 100 ; E-geo, C-geo, F-geo : 200 chacun. Avec 200 couvertures, une borne basse de Wilson de 0,92 exige 192 réussites (96 %), comme en 1quater ; un seuil plus bas est possible pour G (section 10), car le résultat géométrique attendu est plus modeste.
- **Exploratoire contre confirmatoire.** Les tirages de développement et le choix de la grille sont exploratoires ; la configuration est gelée avant E-geo, puis C-geo et F-geo sont à un seul passage.
- **Graines.** Une graine par source d'aléa ; une séparation stricte entre apprentissage et test pour D.

## 9. Procédure et budget

La piste S précède les mesures finales de D et de G, car elle fixe le format ; les pistes D et G peuvent démarrer leurs étapes exploratoires en parallèle.

| Étape | Piste | Contenu | Sortie |
| --- | --- | --- | --- |
| 0 | toutes | gel, commit, manifestes, F mesuré sur le sérialiseur réel | hash du commit |
| 1 | S | spécification V1 des données associées et choix I0 ou I1 (S-1, S-2) | format figé |
| 2 | S | falsification et rejeu, V0 puis V1 (S-3) | G-S1 |
| 3 | S | secret après compromission de clé (S-4) | G-S2 |
| 4 | S | contrôle d'intégrité du message, I0 et I1 (S-2) | G-S3 |
| 5 | S | modèle symbolique, si fait (S-5) | note |
| 6 | D | fuite de longueur sur D-msg (D-1) | G-D1 |
| 7 | D | flux R0 et R1, classifieurs (D-2, D-3), empreinte (D-4) | G-D2 |
| 8 | G | confirmation du régime (G-0), bassin sur D-b (G-2), mesure du coût sur 5 couvertures (G-4) | grille retenue, G-G1 |
| 9 | G | recherche validée sur D-b (G-3), puis gel | configuration figée |
| 10 | G | validation sur E-geo, un seul passage | G-G2 |
| 11 | G | phase finale sur C-geo et F-geo, un seul passage chacun | G-G3 |

**Budget de calcul (estimations, non mesurées).**

- **S.** Quelques minutes pour les 9 classes de mutation et les 52 000 basculements de bit : un déchiffrement AEAD est très court devant la construction d'un record.
- **D.** Les 1 000 records par représentation exigent un codebook par record, soit environ 1 000 × 0,43 s ≈ 7 min par représentation ; la capture réseau est négligeable devant ce calcul.
- **G, par candidat.** On suppose que le coût d'une lecture est proportionnel au nombre de positions lues : 123 positions sur 1 764, soit environ 123 / 1 764 × 0,43 s ≈ 30 ms par candidat. L'hypothèse de proportionnalité est à vérifier à l'étape 8.
- **G, grille complète.** Une grille de 54 043 candidats coûterait environ 27 min par décodage, soit environ 180 h pour 400 décodages (100 couvertures × 4 messages) : elle n'est pas exécutable. Le plafond de 60 s par décodage borne la grille à environ 2 000 candidats. Si le bassin de G-2 exige davantage pour le domaine, on réduit le domaine et on le documente.
- **G, volume.** La recherche porte sur 4 messages (un par famille) : 100 × 4 × 60 s ≈ 6,7 h sur D-b ; 200 × 4 × 60 s ≈ 13,3 h par jeu de validation ou de phase finale, soit environ 47 h au total au pire cas. La mesure du bassin (G-2) n'exige qu'un candidat par condition.

**Points d'arrêt.** Arrêt à la fin d'une étape si sa barrière n'est pas verte. Aucune mesure finale de D ou de G ne commence avant G-S1 ; E-geo, C-geo et F-geo restent fermés avant les étapes 10 et 11.

## 10. Barrières et feux

Chaque seuil est fixé avant exécution. Ceux de D et de G sont des choix de conception, justifiés par la largeur des intervalles et non par une norme ; un écart après coup est consigné comme post hoc.

| Barrière | Verte | Orange | Rouge |
| --- | --- | --- | --- |
| G-S1, falsification et rejeu | zéro acceptation sur tous les essais de V1 | zéro acceptation mais une classe rejetée par un mécanisme autre que celui prévu | une acceptation ou plus : corriger puis rejouer l'ensemble |
| G-S2, secret après compromission | aucun déchiffrement après fuite des clés d'identité ; clés éphémères effacées | — | déchiffrement réussi, ou clés éphémères conservées |
| G-S3, intégrité du message | aucun message faux accepté ; contrôle retenu selon K × 2⁻³² | — | un message faux accepté |
| G-D1, fuite de longueur | descriptif : HD1 confirmée ou non | — | — |
| G-D2, détectabilité de R1 | borne haute de l'IC de l'AUC ≤ 0,60 pour tous les modèles et transports | de 0,60 à 0,70 | > 0,70 |
| G-G1, bassin | descriptif : largeur du bassin et grille déduite | — | — |
| G-G2, validation géométrique (E-geo) | borne basse du succès exact ≥ 0,80 pour au moins deux des trois familles | une seule famille | aucune |
| G-G3, phase finale (C-geo, F-geo) | borne basse ≥ 0,80 sur les deux corpus, pour au moins deux familles | un seul corpus, ou écart entre corpus > 0,10 | aucun corpus |

La représentation R0 est rapportée sans barrière : sa détectabilité mesurée est un résultat, pas un seuil.

### Lecture pour le manuscrit

| Critique | Verte | Orange | Rouge |
| --- | --- | --- | --- |
| Sécurité de bout en bout | levée dans le périmètre testé : G-S1 à G-S3 verts | levée partiellement, avec la classe en cause nommée | non levée, défaillance documentée et corrigée |
| Détectabilité réseau | non détecté par les modèles testés sur ce corpus | détecté faiblement, limite documentée | détecté, à présenter comme limite |
| Synchronisation géométrique | récupération exacte sur la plage bornée testée | une famille seulement | limite maintenue |

Aucune ligne n'autorise « indétectable », « prouvé sûr » ou « robuste à toute transformation » ; l'article doit nommer la plage, le corpus et les modèles testés.

## 11. Menaces à la validité et replis

| Menace | Parade |
| --- | --- |
| Tests de sécurité écrits par le concepteur du format | classes générées de manière systématique sur chaque champ ; balayage exhaustif des basculements d'un bit ; relecture de la spécification V1 par une personne qui ne l'a pas écrite, recommandée |
| Chemins de code non testés | revue du code et, si possible, fuzzing du décodeur ; les chemins non couverts sont listés |
| Corpus de référence TLS non représentatif de l'environnement cible | corpus et date de capture rapportés ; aucune conclusion hors de ce corpus |
| Flux FHAM capturés sur réseau local, sans le bruit d'un réseau réel | transport TCP direct et TLS 1.3 comparés ; limite énoncée |
| Adversaire qui entraînerait un classifieur spécialisé sur R1 | meilleur des modèles, choisi hors du test ; jamais « indétectable » |
| Classe de capacité définie pour 100 octets sources seulement | les autres longueurs de message ne sont pas couvertes et peuvent fuir ; limite énoncée |
| Maximum optimiste sur la grille et le pas de recherche | choix sur D-b, validation sur E-geo, phase finale à un seul passage |
| Référence non transformée peut-être indisponible au récepteur | deux régimes mesurés (G-ref, G-aveugle) tant que G-0 n'est pas tranché |
| Domaine de recherche réduit par le budget de calcul | domaine effectif rapporté ; aucune revendication au-delà |
| Faux accept du contrôle d'intégrité | borne K × 2⁻³² calculée pour la grille retenue ; I1 si elle est trop grande |
| Recherche mesurée sur 4 messages seulement | généralisation limitée aux familles testées |
| Combinaison géométrie et compression non testée | une seule composition (rotation puis JPEG 65) au jeu scellé, rapportée à part |
| Disponibilité des images fraîches pour E-geo, C-geo et F-geo | vérification des manifestes avant le gel ; sinon, jeux plus petits et IC plus larges, annoncés |

**Replis.**

- **S rouge.** Le format est corrigé et l'ensemble des tests est rejoué ; aucune réponse à la critique de sécurité n'est rédigée avant un résultat vert.
- **D rouge.** L'article présente la détectabilité des records comme une limite mesurée, avec la représentation à taille fixe et son coût, et ne revendique pas d'indétectabilité.
- **G rouge.** La géométrie reste une limite : FHAM est présenté pour des canaux sans transformation géométrique, ou en mode catalogue.
- **Dans tous les cas**, le manuscrit énonce que chacune des trois critiques est levée dans un périmètre précis ou reste ouverte, sans formule générale.

## 12. Livrables

**Fichiers.** Un CSV par piste : S (une ligne par essai de mutation, avec la classe, le résultat et le mécanisme de rejet) ; D (une ligne par flux, avec la représentation, le transport, les caractéristiques et le score de chaque modèle) ; G (une ligne par couverture, message, transformation et chaîne, avec le succès, le nombre de candidats et le temps). Manifestes SHA-256 des jeux et des pcap, hash du commit, versions des bibliothèques, graines.

| Livrable | Contenu |
| --- | --- |
| Spécification V1 | champs, données associées, contrôle d'intégrité retenu, paramètres liés |
| T1 | taux d'acceptation des mutations par classe, V0 et V1, avec bornes |
| T2 | secret après compromission de clé, scénarios et résultats |
| T3 | I0 contre I1 : surcoût et borne de faux accept |
| T4 | fuite de longueur : exactitude et information mutuelle |
| T5 | AUC et TPR à 1 % de FPR par modèle, représentation et transport |
| T6 | surcoût de R1 en bits par octet source et ratio face à AES-GCM avec zlib-9 |
| T7 | bassin de réussite et grille retenue |
| T8 | succès exact par chaîne (P1 à P4) et par famille de transformations |
| T9 | validation et phase finale, avec IC et écarts |

**Figures.** Succès en fonction de l'erreur d'angle, d'échelle et de décalage ; courbes ROC de D ; distribution des longueurs de record par famille, avant et après remplissage.

**Page de décision.** Une page : feux de chaque barrière, lecture pour chacune des trois critiques, configuration retenue, écarts avec ce protocole classés comme post hoc, et suite recommandée pour le manuscrit.
