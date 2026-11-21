# Étape 2 FHAM — addendum de correction et gel du protocole

**Version de gel : 1.2 — 21 novembre 2026**
**Source examinée :** `FHAM_etape_2_source_2026-11-21.md`
**SHA-256 de la source :** `BE2FD2D16C5FFB366ABEBECD92B15B3FC53552550A1147DED66264DE305EA061`

Cet addendum fait partie du protocole gelé et prévaut sur toute formulation contradictoire du document source. Il fixe les paramètres avant toute nouvelle mesure. Les seuls préalables autorisés avant son commit sont l’inspection statique du code, des manifestes, des fichiers de résultats existants et des archives; aucune nouvelle mesure S, D ou G n’est lancée avant le commit du protocole et du format V1.

## 1. Résultats de 1quater conservés en lecture seule

La configuration reste `p=10 %`, `q=5 %`, `m=2`, `B=4`, C-moyenne, `L=12`. Aucun résultat de 1quater n’est réexécuté ni modifié. Le registre d’images E/C/F de 1quater demeure exclu des nouveaux jeux géométriques.

## 2. Format réel V1 — remplace les descriptions incomplètes des sections 2–3

Le profil expérimental est un record FHAM authentifié sous AES-GCM, au-dessus d’un échange X25519 signé par des identités Ed25519 provisionnées et vérifiées par épinglage. Un catalogue ordonné de couvertures canoniques (100 entrées pour D-b, au plus 200 pour G) est prépartagé. Pour chaque segment, l’émetteur désigne deux identifiants de catalogue, puis l’indice `0` ou `1` de la couverture choisie; le destinataire possède le même catalogue et son ordre. Cette désignation est chiffrée dans le record. Le coût de provisionnement, de distribution et de renouvellement du catalogue est hors taille du record et reste explicitement une hypothèse.

### 2.1 En-tête public et données associées

L’en-tête public V1 est sérialisé en ordre réseau :

| Champ | Taille |
| --- | ---: |
| magic `FHQ2` | 4 octets |
| version du record (`2`) | 1 octet |
| mode (`R0` compact ou `R1` à capacité fixe) | 1 octet |
| identifiant de session | 16 octets |
| numéro de séquence | 8 octets |
| nonce AES-GCM | 12 octets |
| capacité publique en symboles codés (`0` en R0, `140` en R1) | 2 octets |

Longueur de l’en-tête : 44 octets; étiquette AES-GCM : 16 octets. Le cadrage applicatif existant est `!4sBBI`, soit 10 octets par frame; les couches transport et TLS sont mesurées séparément.

Les données associées sont la concaténation canonique, sans séparateurs variables, du domaine ASCII `FHAM-1quater-V1-AAD`, de l’en-tête public (44 octets), du digest ordonné de catalogue (32), de l’époque attendue du récepteur (`uint32`), et des paramètres en ordre réseau (`version:uint8,m:uint8,p:uint8,q:uint8,B:uint8,L:uint8,descriptor_id:uint8,mode:uint8,capacity:uint16,integrity_id:uint8`, soit 11 octets). Le digest du catalogue est `SHA-256("FHAM-CATALOG-v1" || count:uint16 || digest_0 || … || digest_(count−1))`, avec count en ordre réseau; chaque digest de couverture reprend la définition du dépôt `reference_digest` : domaine ASCII `FHAM-CANONICAL-REFERENCE-v1`, hauteur et largeur `uint32` big-endian, pixels grayscale `uint8` contigus en ordre C. L’identifiant de session est déjà dans l’en-tête. Les longueurs et l’ordre sont non ambigus.

L’en-tête interne de 56 octets est sérialisé sans padding ni champs optionnels : magic `FH` (2), version (1), mode (1), hauteur et largeur `uint16` (4), paramètres `m,p,q,B,L,descriptor_id,integrity_id` (7), longueurs source/compressée/mot RS/nombre placé `uint16` (8), nombre de segments (1), puis deux entrées de segment (longueur source `uint8`, compressé `uint16`, mot RS `uint16`, identifiant couverture 0 `uint8`, identifiant couverture 1 `uint8`, indice choisi `uint8`, soit 8 octets chacune), et digest I1 (16). La somme est 56 octets. Les deux couvertures candidates et le choix sont sérialisés par segment, car A4 peut sélectionner une paire et une couverture différentes à chaque segment. Les messages d’évaluation font 100 octets et sont découpés en deux segments source de 50 octets. Chaque segment est compressé séparément par zlib-9, puis codé séparément par RS avec `parity=ceil(0,10×compressed_segment_length)`, `RSCodec(parity,nsize=255,fcr=0,generator=2,prim=0x11D,c_exp=8)`; un segment sans parité est transmis sans RS. I1 est SHA-256 tronqué à 128 bits des deux segments compressés concaténés dans l’ordre, vérifié après décodage RS et avant zlib. Chaque slot de 16 bits est `erasure:uint1 || token:uint11 || residual:uint4`; `residual=δ+4` pour un symbole placé, et token/résidu valent zéro pour un effacement ou un slot de remplissage. Le bit d’effacement distingue ces cas. La valeur M=1764 tient dans 11 bits; ce codage n’est applicable qu’à BOWS2 256×256. Le digest ordonné de tout le catalogue est dans l’AAD; après déchiffrement, le récepteur vérifie que les deux IDs sont distincts et valides, que l’indice choisi vaut 0 ou 1, puis compare l’image reçue au digest de la couverture choisie.

### 2.2 I1 retenu; I0 reste un comparateur

Le record V1 utilisé pour D et G contient I1 : les 128 bits de tête de `SHA-256` des deux segments compressés concaténés avant Reed–Solomon. Le contrôle est vérifié après décodage RS et avant décompression. I0, CRC-32 des mêmes octets compressés, est mesuré uniquement comme comparateur de taille et de taux de faux accept; il n’est pas le validateur du mode V1.

La borne de faux accept pour I1 et `K` candidats est `K·2⁻¹²⁸`. Avec la limite gelée `K≤2 000`, elle est au plus `5,88×10⁻³⁶` par recherche. Le CRC-32 n’est pas retenu pour P4 : à 54 043 candidats, sa borne serait `1,26×10⁻⁵` par recherche.

### 2.3 Modes de record et taille R1

- **R0 compact :** header interne de 56 octets suivi des slots de 16 bits pour chaque symbole codé; la séquence complète est compressée par zlib niveau 9, puis chiffrée et authentifiée. Le cadrage réseau révèle sa longueur. Le coût est mesuré sur le record complet.
- **R1 fixe :** capacité de 140 symboles codés; header interne de 56 octets; 140 mots de 16 bits. Cette capacité couvre deux segments source de 50 octets : `zlib.compressBound(50)≤63`, puis `ceil(0,10×63)=7` octets de parité par segment, soit au plus 70×2=140 symboles. Toute taille réellement observée est vérifiée contre cette borne avant le réseau. Pour BOWS2 256×256, chaque mot encode 1 bit d’effacement, 11 bits de jeton (M=1 764) et 4 bits de résidu (δ∈[−4,+4], codé δ+4). Un symbole non placé ou un slot de remplissage porte le bit d’effacement à 1 et un jeton/résidu nul; un symbole placé porte le bit à 0. Le plaintext fixe fait `56+140×2=336` octets. Il n’est pas compressé après encodage. Le record AEAD fait `44+336+16=396` octets; avec le frame de 10 octets, le record applicatif fait 406 octets, hors surcouches TLS/TCP/IP. La mesure R1 utilise les couvertures BOWS2 à M=1 764; cette représentation compacte à 16 bits/symbole n’est pas déclarée applicable à BOSSBase M=7 056. En comparant I0 à I1 sous R1, le CRC-32 est suivi de 12 octets nuls dans le champ de digest de 16 octets; la taille ne change pas. Le CRC reste un comparateur pour erreurs aléatoires et ne constitue pas une authentification résistante à un adversaire.
- Avant tout envoi, les 8 000 messages D-msg sont compressés et codés. R1 est faisable seulement si chaque mot codé tient dans 140 slots. Une violation de la borne `compressBound` arrête R1; aucun message n’est silencieusement exclu ou tronqué.
- La comparaison de coût AES direct comprend deux baselines : AES-GCM sur source brute (`29` octets d’enveloppe) et AES-GCM après zlib-9 appliqué à la même source. Les ratios sont rapportés par famille. Le prétraitement galerie est exclu des deux formats et signalé comme coût partagé non mesuré.

### 2.4 Clés et handshake

Chaque session utilise de nouvelles clés éphémères X25519, un identifiant aléatoire de 16 octets et une époque de réception `uint32` fournie par l’état monotone du récepteur. Chaque offre porte un rôle (`0=émetteur,1=récepteur`), l’identifiant de session, la clé X25519 publique et l’époque (53 octets); la signature Ed25519 de 64 octets porte ces champs, les identités épinglées des deux pairs et le domaine `FHAM-X25519-OFFER-v2`. Chaque offre fait 117 octets et est encadrée par un header applicatif de 10 octets (`magic=FHAM, version=2, type[1], payload_length:uint32`, ordre réseau; types `1=offer,2=confirm,3=record`). Le transcript SHA-256 contient les deux offres signées dans l’ordre rôle 0 puis rôle 1, le digest de galerie et les paramètres fixes. HKDF-SHA256 avec salt=`session_id` dérive deux clés AEAD directionnelles de 32 octets et deux clés de confirmation directionnelles de 32 octets, chacune avec son label distinct et le transcript comme contexte. Chaque confirmation est `HMAC-SHA256(K_confirm_direction, transcript || role)` (32 octets); avant tout record, chaque pair valide la confirmation de l’autre. Aucune clé AEAD n’est utilisée avant validation. Aucun nonce AES-GCM n’est réutilisé sous une même clé; la génération est aléatoire CSPRNG et les cinq séquences d’une session sont contrôlées pour doublon. Le handshake ajoute 234 octets d’offres, 64 octets de confirmations et 40 octets de framing, soit 338 octets avant les couches transport/TLS; les longueurs produites par le sérialiseur et observées dans les captures prévalent.

Le format V1 lie le transcript, les identités et la galerie à la session. La compromission ultérieure des seules clés d’identité ne doit pas permettre le déchiffrement rétrospectif. Les objets de clés éphémères ne sont ni écrits sur disque ni conservés après clôture de session; le code Python ne permet pas de garantir l’effacement physique de leur mémoire, et le rapport ne le revendique pas.

### 2.5 Rejeu et état persistant

Le garde SQLite est le mécanisme de mesure, avec séquence stricte et validation atomique. Chaque session est enregistrée avant son premier record; les records dupliqués, réordonnés, sautés ou d’une session inconnue sont rejetés. Le test ferme et rouvre le processus et la base. La restauration d’un snapshot ancien est testée avec une époque monotone distincte, fournie par un état de confiance externe et signée dans le contexte de session. L’exigence de stockage monotone dans un déploiement est déclarée; une base SQLite seule ne protège pas d’un rollback de sauvegarde.

## 3. Piste S — tests confirmatoires et interprétation

V0 est l’ancien record de session mono-couverture; il sert de témoin pour les classes qu’il sait représenter. Pour les mutations de galerie et paramètres propres à V1, V0 est noté « non applicable », jamais compté comme un échec ou un succès. V1 est le format réellement transmis pour les expériences suivantes.

- Tester 1 000 mutations par classe définie en section 3 du document source, avec génération reproductible : en-tête, nonce, ciphertext, tag, troncature/extension, session, séquence, couverture, galerie/ordre, paramètres et offre signée.
- Réaliser le balayage exhaustif d’un bit sur 20 records produits par le sérialiseur V1. Rapporter le nombre exact de bits parcourus à partir des longueurs produites; « environ 52 000 » n’est pas une valeur fixe.
- Tester rejeu, séquence hors ordre, session étrangère, fermeture/réouverture, base vierge et snapshot restauré. Toute acceptation non prévue est une défaillance; aucune barrière n’est évaluée sur le seul test nominal.
- Tester fuite ultérieure des identités, indépendance des clés de sessions, usurpation de l’autre pair et authentification des offres. Le test de clé établit le comportement du code dans ces scénarios, pas une preuve formelle de sécurité.
- Comparer I0/I1 avec les mêmes 20 records en R0 et R1; rapporter l’écart réel après compression pour R0 et le surcoût nul en longueur du record fixe R1. V1/D/G restent en I1. Les nombres d’essais, tailles et bornes de confiance sont calculés sur les sorties effectives.
- S1/S2/S3 verts s’entendent uniquement pour les classes d’essais et le modèle de menace ci-dessus. Pas de revendication de preuve formelle, d’implémentation TLS complète ou de résistance à une compromission active du canal de distribution de galerie.

## 4. Piste D — détection et fuite de longueur

### 4.1 Messages et tailles d’échantillon

`D-msg` commence par **10 000 candidates de message de 100 octets**, soit 2 500 par famille (répétition adversariale, texte naturel, ASCII imprimable, octets uniformes), avec graine publiée, identifiant et SHA-256; elles sont disjointes des 12 messages 1quater. La classe « un octet répété 100 fois » ne peut avoir que 256 contenus distincts, donc plusieurs identifiants peuvent porter le même contenu. Pour chaque message, classer les 100 IDs D-b par `SHA-256("FHAM-DPAIR-v1" || message_SHA256 || cover_id:uint8)` croissant et retenir les deux premiers dans cet ordre; cette paire ne dépend d’aucune mesure. Mesurer ensuite la faisabilité avec cette paire exacte. Dans chaque famille, les 2 000 premières candidates faisables selon l’ordre SHA-256 préenregistré forment D-msg; le taux de faisabilité et les candidates non transmises sont rapportés. Si une famille fournit moins de 2 000 faisables, D ne démarre pas et aucune candidate n’est ajoutée après examen des tailles ou scores. Toute répartition train/validation/test groupe les messages de même SHA-256 dans une seule partition; D-1 groupe les plis par SHA-256. Pour chaque condition D-3, les 8 000 instances sont utilisées une fois chacune, cinq par session, un message de 100 octets par record : cela donne exactement 1 600 sessions et 8 000 records. Le même découpage par contenu est appliqué aux quatre conditions. La longueur 100 octets est l’unique longueur évaluée.

### 4.2 Sessions et contrôles réseau

Les quatre conditions FHAM sont `R0×TCP`, `R1×TCP`, `R0×TLS 1.3`, `R1×TLS 1.3`. Pour chaque condition, produire 1 600 sessions positives, chacune avec cinq records successifs issus de cinq instances D-msg distinctes : 400 sessions train, 200 validation, 1 000 test. Produire le même nombre de sessions négatives appariées par transport et partition, avec cinq messages applicatifs ordinaires de 100 octets, sans format ni handshake FHAM; les contrôler par volume source, calendrier d’émission et famille de contenu. Une session/TCP-flow est l’unité d’observation et de bootstrap; les cinq records ne sont jamais comptés comme cinq flux indépendants.

Le corpus non-VPN ISCX de l’article est une **référence externe secondaire**, 1 000 flows au plus, échantillonnée par capture et figée par SHA-256. Il est rapporté séparément des contrôles appariés, car son époque TLS, ses applications et sa capture diffèrent de celles du générateur local. Les archives `D:\dataset\NonVPN-PCAPs-01.zip`, `-02.zip`, `-03.zip` sont l’origine; aucun décompactage global sur le disque système. Les caractéristiques agrégées existantes ne sont réutilisées qu’après vérification de leur script, de leurs labels, de leur empreinte et de leur correspondance aux archives.

Ainsi, la taille de test de la comparaison principale est de 1 000 sessions par classe et par condition; cela donne 4 000 sessions FHAM positives et 4 000 contrôles appariés dans les quatre jeux de test, sur 6 400 sessions de chaque classe produites au total. Chaque session comporte cinq records, soit 32 000 émissions FHAM au total et 20 000 dans les jeux de test. Les 8 000 instances D-msg alimentent chacune des quatre conditions; elles sont réutilisées entre conditions R0/R1 et TCP/TLS, jamais entre partitions d’une même condition. Les SHA-256 identiques de la famille répétée restent assignés à une seule partition dans toutes les conditions.

### 4.3 Modèles et baselines

D-1 utilise quatre classes équilibrées, 2 000 messages par classe, longueur de record seule, validation croisée groupée par message et information mutuelle empirique avec bootstrap par message.

D-3/D-4 utilisent tailles/sens des paquets, volumes, nombre de paquets, délais, durée, longueurs/sens des enregistrements TLS disponibles et un détecteur déterministe des marqueurs applicatifs V1 (`FHAM` version 2 et `FHQ2`). Le détecteur de marqueur est rapporté séparément; sur TCP brut, ces marqueurs sont visibles par définition. Régression logistique, forêt aléatoire, gradient boosting et classifieur de volume total. Partitions train/validation/test groupées par session; aucun réglage sur test. 10 000 bootstraps par session. Les seuils AUC du document source s’appliquent à la comparaison principale appariée; la référence externe est descriptive.

Le handshake réellement nécessaire à l’établissement des clés (deux offres signées, deux confirmations) est inclus dans chaque session positive et compté dans les caractéristiques. Il est transmis comme messages de contrôle séparés; le protocole ne place pas une offre dans un record déjà chiffré avec les clés qu’elle sert à établir. Le résultat est distinct pour TCP brut et TLS 1.3. Le framing TCP brut et les enregistrements TLS sont décrits séparément. On ne décrit jamais un résultat AUC proche du hasard comme « indétectable ».

## 5. Piste G — régime applicable, messages et jeux

- Le mode supporté est **G-ref** : le destinataire possède le catalogue canonique. Il déchiffre d’abord le record, lit pour chaque segment la paire d’IDs et l’ID choisi, vérifie l’image reçue contre cette référence canonique, estime la similarité par ORB/RANSAC, puis recherche localement. **G-aveugle** n’est pas un mode FHAM applicable, car sans référence canonique le destinataire ne peut pas reconstruire le dictionnaire de hachage. P1 sans recalage, P2 ORB/RANSAC, P3 inverse oracle et P4 recherche validée restent comparés.
- La transformation recherchée est une similarité à quatre paramètres (rotation, échelle uniforme, translations x/y). Le modèle ORB/RANSAC est fixé en développement; une homographie à huit degrés de liberté n’est pas substituée après mesure.
- Les messages géométriques sont les quatre messages 100 octets index `00`, un par famille, fixés avant les mesures. D-b sert au bassin G-2; E-geo à la validation; C-geo et F-geo aux passages finaux. La généralisation est explicitement limitée à ces quatre messages.
- Les jeux E-geo et C-geo contiennent chacun 200 images distinctes tirées par classement SHA-256 du partage BOWS2-C restant après les 200 images déjà utilisées par 1quater. F-geo contient 200 images BOSSBase distinctes des 400 candidates précédentes et des 200 images F de 1quater. Manifestes, partitions et empreintes sont gelés avant toute lecture des pixels; si un fichier manque ou son hash diffère, arrêt du corpus sans remplacement.
- Conditions : rotation, recadrage-restauration, réduction-restauration selon les plages de la section 5 du document source; validation +1°, crop 5 %, scale 0,8; test scellé −1,25°, crop 9 %, scale 0,75 et rotation puis JPEG 65 rapportée séparément. Géométrie seule porte les barrières; la composition avec JPEG n’en porte aucune.
- P4 valide la reconstruction par I1 (SHA-256 tronqué 128 bits) à chaque candidat. Le budget maximal reste 2 000 candidats et 60 s par décodage; la grille et ses points exacts sont gelés sur D-b avant E-geo. Si le bassin exige plus, le domaine est réduit et nommé, sans prétendre couvrir la plage non mesurée.
- G-G2/G-G3 gardent les seuils du document source. La cellule d’analyse est une couverture; les IC bootstrap (10 000) sont primaires. Wilson et résultats par message sont aussi rapportés. Pas d’extrapolation entre BOWS2 et BOSSBase.

## 6. Sévérités, comptages et écarts corrigés

Les corrections suivantes prévalent sur le document source :

1. D-msg a 10 000 candidates (4×2 500) et 8 000 instances faisables retenues (4×2 000), et non 800 ni 4×100. Elles alimentent 1 600 sessions de cinq records par condition; les contenus identiques de la famille répétée sont groupés ensemble lors des partitions. Les taux de faisabilité des candidates sont publiés.
2. Le plan réseau distingue sessions, flows et records : 1 600 sessions positives par condition; 1 600 contrôles appariés; 1 000 sessions par classe restent en test. « 1 000 flux et 200 sessions » ne sont pas assimilés.
3. Le surcoût du handshake est mesuré sur le sérialiseur et les captures produits; la valeur supposée de 208 octets n’est pas utilisée. V1 spécifie deux offres de 117 octets et deux confirmations de 32 octets, plus quatre frames de 10 octets; le total théorique est 338 octets et la taille réellement produite est consignée.
4. R1 chiffre 336 octets internes fixes (56 octets de champs et 140 mots de 16 bits), pour un record AEAD de 396 octets et un record applicatif de 406 octets hors surcouches TLS/TCP/IP. Le budget des slots est de 22,4 bits/octet source avant les headers, le digest, l’AEAD et le framing.
5. La grille illustrative CRC de 54 043 candidats donne `54 043/2³² ≈ 1,26×10⁻⁵`, et le domaine complet est plus grand; V1/P4 utilise I1.
6. Le coût de 0,43 s par codebook n’est pas utilisé comme coût de décodage d’une transformation. Le temps P4 est mesuré sur cinq couvertures et les vrais candidats; le budget est recalculé avec ces mesures avant E-geo.
7. Les résultats JPEG 65 et σ=2,5 ne sont pas supposés exister. S’ils ne sont pas produits dans cette étape, ils sont enregistrés comme non exécutés; aucune valeur ne sera appelée extrapolation mesurée.
8. Les résultats des pilotes réseau existants et de 1quater sont des références antérieures, pas des observations de ce protocole V1.

## 7. Ordre d’exécution gelé

1. **S-0 :** commit du protocole et du format V1, mesures du sérialiseur, manifestes et SHA-256.
2. **S :** implémenter V1; exécuter G-S1 à G-S3 et enregistrer les résultats. Une défaillance de format suspend D; corriger, consigner la première passe puis rejouer S avant d’autoriser D.
3. **G développement en parallèle après le gel du format :** G-0, bassin G-2 sur D-b, mesure de coût cinq couvertures, choix/gel de la grille P4. Les jeux E-geo/C-geo/F-geo restent fermés.
4. **D après sécurité verte :** générer D-msg; mesurer fuite de longueur; capturer les sessions R0/R1 TCP et TLS 1.3 avec le handshake V1 réellement défini; entraîner sur train, choisir le meilleur sur validation, tester une seule fois.
5. **G validation :** ouvrir E-geo après gel de la grille, un passage; si G-G2 n’est pas vert, arrêt avant C-geo/F-geo.
6. **G phase finale :** C-geo et F-geo un seul passage chacun après G-G2 vert. Consigner G-G3 et les sévérités non exécutées.

Le modèle symbolique ProVerif reste facultatif; s’il n’est pas exécuté, il est explicitement listé comme non fait. Une revue par une personne indépendante du format est recommandée; elle n’est pas présentée comme accomplie sans preuve.

## 8. Faits du dépôt et des données à tracer dans le manifeste de gel

- `AuxiliaryChannel.protect` emploie une AAD constante. `protect_session` lie le digest d’une image unique et l’en-tête de session, mais pas la galerie ordonnée ni `(p,q,m,B,L,descripteur)`.
- `derive_session_key` emploie actuellement un contexte HKDF constant, sans séparation explicite des directions ni hash de transcript. `ReplayGuard` est en mémoire; `SQLiteReplayGuard` persiste les séquences mais n’empêche pas seul le rollback d’un snapshot.
- Le pilote `traffic_transport_pilot.py` utilise un profil historique B=2 et des messages de 40/200 caractères; il n’est pas le test de D pour 1quater.
- Le pilote ORB/RANSAC de l’étape 1 est un diagnostic antérieur; P4 et sa recherche de similarité V1 sont nouveaux.
- Les archives NonVPN sont actuellement présentes sous `D:\dataset` en trois ZIP (23, 26 et 60 captures PCAP/PCAPNG, soit 109). Aucun PCAP n’est extrait dans ce dossier. Le protocole utilise les archives en lecture seule et les caractéristiques de trafic existantes seulement si leurs scripts, labels, SHA-256 et correspondances sont contrôlés; l’extraction complète n’est pas un prérequis.
- Les partitions image ont la capacité attendue d’après les manifestes hash-only : BOWS2-C a 6 925 candidats restants après les 200 images C de 1quater; BOSSBase a plus de 200 images éligibles après exclusion des 400 candidates antérieures et des 200 images F. Ces comptes sont revérifiés au gel effectif.

## 9. Barrières d’arrêt

Les barrières G-S1/S2/S3, G-D1/D2 et G-G1/G2/G3 restent celles des sections 3, 4, 5 et 10 du document source, sauf définitions d’échantillon et de format corrigées ici. Toute mesure est rapportée même si elle échoue. Les jeux finaux restent scellés jusqu’au passage prévu. Aucune revendication « sûr », « indétectable » ou « robuste à toute géométrie » n’est permise.
