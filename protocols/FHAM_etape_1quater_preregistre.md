# FHAM — Protocole de l'étape 1quater : déficit d'affectation, effacements et repli de l'émetteur

Nov 20, 2026 · @Ekodeck Stéphane

## 1. Objectif, point de départ et questions

L'étape 1quater cherche à savoir si le déficit d'affectation, et non la justesse après affectation, peut être réparé par trois leviers : l'affectation partielle avec effacements corrigés par Reed–Solomon, le remplissage « robustes d'abord », et le repli de l'émetteur (choix d'une couverture ou découpage du message).

**Statut du document (20 novembre 2026).** Protocole relu et corrigé avant gel : D6/D7 sont post hoc sur D-a ; les entrées D-b et les messages sont figés par SHA-256 avant toute mesure A1–A5.

### Point de départ (1ter, BOWS2-D, 256 × 256, L = 12, B = 8, 100 couvertures)

| Grandeur | Spectral | C-moyenne | C-DCT |
| --- | --- | --- | --- |
| Fraction robuste moyenne | 6,81 % (120 positions) | 26,12 % (461 positions) | 16,70 % (295 positions) |
| Couvertures faisables pour les 12 messages | 2 % | 68 % \[58,34 ; 76,33\] | 47 % \[37,51 ; 56,71\] |
| Faisabilité par message | non rapportée | 72 à 95 % | 52 à 87 % |
| Justesse conditionnelle (JPEG 75, bruit σ = 2) | — | ≥ 99,51 % | ≥ 99,25 % |
| Justesse effective (JPEG 75) | — | 77,74 % \[69,87 ; 84,95\] | 61,19 % \[52,61 ; 69,49\] |
| Paires (couverture, valeur) sans candidat à ± 8 | 9,21 % | 1,01 % | 3,34 % |

Ce que 1ter n'a pas mesuré : le déficit d'affectation (longueur comprimée moins taille du couplage maximal), la faisabilité en fonction de la longueur source et tout résultat à 512 × 512. BOSSBase offre 7 056 positions à L = 12 contre 1 764 pour BOWS2 ; les deux corpus restent séparés.

### Questions

- **Q1.** Quelle est la distribution du déficit d'affectation, et quelle part des échecs vient d'octets sans candidat plutôt que de la saturation de Hall ?
- **Q2.** Comment la faisabilité varie-t-elle selon L_src (25, 50, 100, 200 octets source), et quelle est la capacité maximale par couverture ?
- **Q3.** L'affectation partielle, les symboles non placés étant déclarés comme effacements corrigés par Reed–Solomon, atteint-elle un succès de communication ≥ 0,95 pour une parité et un coût en bits acceptables ?
- **Q4.** Un remplissage « robustes d'abord » avec une fraction plafonnée d'emplacements non robustes (0, 2, 5, 10 %) lève-t-il la faisabilité sans dégrader la justesse conditionnelle ?
- **Q5.** Un repli de l'émetteur (m couvertures candidates, ou découpage du message) suffit-il, et sous quelle hypothèse d'indépendance ?
- **Q6.** Ces résultats se reproduisent-ils sur BOSSBase à 512 × 512, mesurés séparément ?

### Hypothèses

- **H11.** Pour les messages infaisables, le déficit médian est de 3 symboles ou moins sur environ 100. Réfutée par le diagnostic post hoc : pour C-moyenne à B = 8, la médiane est de 13,5 symboles comprimés (14,82 % de la longueur comprimée).
- **H12.** Affectation partielle plus Reed–Solomon donne un succès de communication ≥ 0,95 avec une parité ≤ 40 % de la longueur de chaque bloc comprimé. Le diagnostic post hoc la rend peu probable : sur D-a, la condition nécessaire d ≤ P n'est satisfaite que dans 92,5 % des cas à B = 8 et p = 40 %, sous 95 % ; elle est mesurée sur D-b, pas présumée.
- **H13.** Une fraction non robuste ≤ 5 % porte la faisabilité par message à ≥ 90 % avec une justesse conditionnelle ≥ 98 %.
- **H14.** Avec m = 3 couvertures et des échecs indépendants, la faisabilité monte à 97,8 % pour un taux par message de 72 % (1 − 0,28³) et à 88,9 % pour 52 % (1 − 0,48³). L'indépendance n'est pas acquise : les couvertures d'une même image ou d'un même corpus partagent des défauts.

### Hors périmètre

Synchronisation géométrique, sécurité de bout en bout, nouveaux descripteurs autres que C-moyenne, ouverture de BOWS2-E, BOWS2-C ou BOSSBase-F avant le gel de la configuration. Les critiques sur la chaîne de communication (association image–métadonnées, rejeu, établissement des clés) ne sont pas levées par ce protocole et se traitent séparément dans l'article et dans la lettre de réponse.

## 2. Préalables : diagnostic de déficit (G-Q0)

Le déficit d'affectation d décide si l'affectation partielle (A2) a un sens : elle n'en a que si d reste petit devant n. Ce diagnostic se calcule sur les sorties de 1ter, sans nouvelle perturbation ; il est post hoc et ne sert pas de confirmation.

Pour chaque couple (couverture, message), avec les seuls emplacements robustes, d = L_c − |couplage maximal|, L_c étant la longueur comprimée avant codage. Le symbole n désigne L_c dans le problème d'affectation ; les courbes A1 sont indexées par L_src, la longueur source en octets. On décompose d en d\_vide, le nombre de symboles sans candidat à ± B, et d\_Hall = d − d\_vide, dû à la saturation.

| Diagnostic | Contenu | Sert à |
| --- | --- | --- |
| D1 | distribution de d (médiane, quantiles 90 et 99, maximum) pour C-moyenne et C-DCT, B ∈ {2 ; 4 ; 8} | Q1, H11 |
| D2 | part des échecs avec d\_Hall = 0 ; histogramme du nombre de valeurs sans candidat par couverture | Q1 : les trous sont-ils concentrés sur peu de couvertures ? |
| D3 | faisabilité par message avec IC bootstrap par couverture, et rapprochement avec la justesse effective de 1ter | cohérence du rapport |
| D4 | rejeu de 4 480 lignes archivées : écart de reproduction | non-régression |
| D5 | bits fixes par symbole : ⌈log₂ M⌉ + ⌈log₂(2B+1)⌉, soit 16 bits à B = 8 pour BOWS2 (11 + 5) et 18 pour BOSSBase (13 + 5) | budget de G-Q2 |

**D6 (diagnostic post hoc déjà exécuté).** Le déficit a été recalculé sur les mots exacts Reed–Solomon (reedsolo 1.7.0) et sur une parité pseudo-aléatoire en sensibilité. À B = 8 et p = 40 %, d ≤ P dans 92,5 % des cas exacts (92,9 % pour la parité aléatoire), sous le seuil G-Q2 de 0,95. Ce résultat sur D-a rend A2 seul peu prometteur sur ces données, sans réduire la grille D-b ni préjuger des combinaisons A3/A4.

**D7 (diagnostic post hoc déjà exécuté).** L'histogramme des hachages robustes et les fenêtres ± B saturées ont été analysés. L'entropie moyenne est 6,760 bits contre 7,395 pour toutes les positions ; à B = 8, 142/224 échecs ont une fenêtre surchargée par une valeur isolée et 82 relèvent d'une compétition entre fenêtres recouvrantes. La remise en forme des symboles n'est pas incluse dans cette étape et nécessiterait un protocole distinct.

### Résultats D6 et D7 (20 novembre 2026, post hoc, D-a)

- **D6.** Avec les mots Reed–Solomon exacts, B = 8, p = 40 % et un canal parfait, d ≤ P dans 92,5 % des cas (parité aléatoire : 92,9 %). Par famille : 98,7 % pour les octets répétés, 91,3 % pour le texte naturel, 89,3 % pour l'ASCII imprimable, 90,7 % pour les octets uniformes. La borne est sous 0,95 : A2 seul est peu prometteur sur D-a.
- **Coût.** b\_assign moyen de 19,22 bits par octet source sur les 12 messages, et 26,52 pour les seuls messages uniformes, ce qui retrouve l'exemple de la section 6.
- **D7.** Entropie moyenne des hachages robustes : 6,760 bits contre 7,395 pour toutes les positions ; support effectif de 119,9 valeurs contre 171,8. À B = 8, 142 des 224 échecs ont une fenêtre saturée par une valeur isolée et 82 relevent d'une compétition entre fenêtres qui se recouvrent. La concentration est réelle mais n'explique pas tous les déficits.

La grille de la section 4 n'est pas réduite après ces résultats : les cellules de A2 seul restent calculées et rapportées.

**Lecture prévue.** G-Q0 est descriptive et ne décide d'aucune branche : A2 est évalué sur D-b avec ses propres barrières (G-Q2). Cette règle remplace deux règles contradictoires de la version précédente (abandon de A2 au-delà de 10 % de n en section 2, poursuite avec p ≥ 30 % entre 10 et 25 % en section 9). Elle est posée après avoir vu le résultat (médiane de d/n : 14,82 %, C-moyenne, B = 8) ; elle n'écarte aucune configuration et ne retient pas la branche favorable, elle supprime seulement un arrêt anticipé.

### Résultats du diagnostic post hoc (18 novembre 2026)

Le couplage maximal reproduit exactement les étiquettes de 1ter (7 200 cas sur 7 200). H11 n'est pas soutenue.

| Descripteur | B | Infaisables / 1 200 | Médiane d | Q90 d | Médiane d/n | d\_vide moyen | d\_Hall moyen |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C-moyenne | 2 | 616 | 7 | 52 | 9,26 % | 9,10 | 8,61 |
| C-moyenne | 4 | 376 | 10 | 54,5 | 13,89 % | 6,96 | 12,58 |
| C-moyenne | 8 | 224 | 13,5 | 55,4 | 14,82 % | 4,39 | 17,02 |
| C-DCT | 8 | 393 | 19 | 72 | 22,52 % | 8,12 | 19,39 |

- Le déficit résiduel de Hall l'emporte : 216 des 224 échecs de C-moyenne à B = 8 ont d\_Hall > 0, et 8 seulement s'expliquent entièrement par des symboles sans candidat. Cela contredit l'idée que les trous d'octets seraient la cause principale.
- Les trous sont concentrés : 13 couvertures sur 100 en ont au moins un, la médiane est nulle, le maximum est de 91 valeurs.
- Un déficit médian de 15 % de n avec un Q90 de 55 symboles rend A2 peu probable à parité ≤ 40 %. Il n'est pas écarté, car d a été calculé sur n symboles et non sur le mot codé (D6).

## 3. Données

Les images de 1ter servent à G-Q0 seulement ; le développement des leviers utilise des images jamais traitées, la validation sur E vient après le gel, et C et F restent scellés jusqu'à la phase finale.

| Jeu | Taille | Rôle | Statut |
| --- | --- | --- | --- |
| D-a | 100 images BOWS2-D (256 × 256) | G-Q0, diagnostic post hoc | déjà exploitées par 1ter |
| D-b | 100 images BOWS2-D restantes | développement des leviers A1 à A4 | absentes des sorties de criblage et de plafond de 1ter ; liste figée par SHA-256 avant le gel |
| E | 200 images BOWS2 (256 × 256) | validation de la configuration gelée | pixels jamais ouverts |
| C | 7 125 images BOWS2 (256 × 256) | phase finale, sous-échantillon de taille N | scellé, pixels fermés |
| F | 200 images BOSSBase (512 × 512) | A5, corpus séparé | réservation hash-only, pixels fermés |

**Règles.**

- Images natives, sans redimensionnement : 1 764 positions à L = 12 pour BOWS2, 7 056 pour BOSSBase. Aucun résultat n'est extrapolé d'un corpus à l'autre.
- Messages : les 12 messages de 1ter (quatre familles × trois indices), comprimés par zlib-9, pour L\_src = 100 octets sources ; pour la courbe A1, les mêmes familles et indices à 50 et 200 octets (fichiers existants) et à 25 octets (les 25 premiers octets des fichiers de 50 octets du même indice, avec contrôle SHA-256 des 12 messages avant le gel).
- Les couvertures candidates de A4 sont tirées dans D-b (développement) puis dans E (validation), jamais dans le même jeu que la configuration qu'elles servent à choisir.
- Les manifestes de E, C et F portent `pixels_opened=false` jusqu'à l'étape qui les consomme ; toute ouverture est consignée avec le hash du commit.
- La taille N de la phase finale suit la règle de la section 7.

## 4. Facteurs

Le descripteur est fixé à C-moyenne (classé premier sur D en 1ter, choix exploratoire), le profil à L = 12 et la robustesse estimée comme dans le criblage de C-moyenne en 1ter (K = 50 tirages JPEG et K = 50 tirages bruit ; un emplacement est robuste s'il ne bascule dans aucun des 100 tirages, et ŝ = (101 − f) / 102 pour les autres, f étant le nombre de basculements sur ces 100 tirages). B = 2 est abandonné (15 % de faisabilité conjointe) ; B ∈ {4 ; 8}.

**Notations et chaîne de codage.** L_src est la longueur source en octets. Après zlib-9, L_c est la longueur comprimée en octets (symboles GF(256)). Sans Reed–Solomon, le mot à affecter a n = L_c symboles. Avec Reed–Solomon, L_c est découpé en blocs source et L_cw = L_c + P désigne le nombre de symboles après parité. A1 est indexé par L_src ∈ {25 ; 50 ; 100 ; 200} ; les déficits d'affectation portent sur L_c sans code ou L_cw avec code. Les blocs ont au plus 128 octets source ; chaque bloc de longueur ℓ_b reçoit P_b = ⌈p·ℓ_b⌉ octets de parité Reed–Solomon raccourci sur GF(256), avec P = ΣP_b. Un bloc codeword compte au plus 128 + ⌈0,4 × 128⌉ = 180 symboles, sous la limite de 255. Un message uniforme de 200 octets sources fait 211 octets comprimés dans les fichiers actuels : deux blocs équilibrés de 106 et 105 octets. Un CRC-32 des L_c octets comprimés est transporté dans le record authentifié (4 octets) pour détecter une mauvaise correction ; il n'est pas affecté à des positions.

| Levier | Définition | Paramètres |
| --- | --- | --- |
| A1, capacité | couplage maximal sur emplacements robustes pour chaque (couverture, message) | L_src ∈ {25 ; 50 ; 100 ; 200} octets source |
| A2, effacements | le message est codé par Reed–Solomon raccourci sur GF(256), puis affecté ; les symboles sans place sont déclarés effacés | parité p ∈ {0 ; 10 ; 20 ; 30 ; 40 %} de la longueur de chaque bloc, arrondie par excès (p = 0 : pas de code) |
| A3, remplissage | étape 1 : couplage maximal sur emplacements robustes ; étape 2 : placer les symboles restants sur les emplacements non robustes de plus grand ŝ ; au-delà du plafond, effacements | fraction non robuste q ∈ {0 ; 2 ; 5 ; 10 %} de L_cw (ou n sans code), plafond arrondi à l'entier inférieur |
| A4, repli de l'émetteur | choix de la première couverture faisable parmi m ; ou blocs de 50 octets, chacun avec son propre choix | m ∈ {1 ; 2 ; 3 ; 5} |
| A5, corpus | mêmes leviers sur BOSSBase 512 × 512, configuration issue de D-b, sans réglage | profil L = 12 (7 056 positions) |

**Configurations testées.** Toutes les combinaisons de p ∈ {0 ; 10 ; 20 ; 30 ; 40 %}, q ∈ {0 ; 2 ; 5 ; 10 %}, m ∈ {1 ; 2 ; 3 ; 5} et B ∈ {4 ; 8}, soit 160 cellules, sont calculées sur D-b et toutes rapportées. A2 seul (q = 0, m = 1), A3 seul (p = 0, m = 1) et A4 seul (p = 0, q = 0) en sont les cas de bord ; sans code (p = 0), les symboles non placés comptent comme des échecs. En A4, m couvertures sont tirées sans remise dans D-b pour chaque tentative, et les couvertures sont réutilisées entre tentatives. L'A4 par blocs de 50 octets est une variante séparée, rapportée à part avec le nombre de couvertures utilisées (une par bloc). La galerie de m couvertures est supposée prépartagée, comme la couverture unique de FHAM ; son coût de distribution n'est pas compté, ce qui réduit la portée de A4.

**Modèle des effacements (A2).** Un code Reed–Solomon corrige e effacements et t erreurs dans un bloc b si e + 2t ≤ P_b, où P_b = ⌈p·ℓ_b⌉ est le nombre de symboles de parité et ℓ_b la longueur du bloc source avant codage. L'émetteur connaît les effacements ; le bitmap de L_cw bits est transporté dans le record authentifié.

**Coût d'affectation.** Dans les trois leviers, parmi les couplages de taille maximale, on minimise D₁ puis on maximise Σ log ŝ (le coût C1 de 1ter). Les paramètres du solveur ne changent pas, pour que seul le levier explique l'écart.

**Chaîne de décodage.** P1 (coordonnées fixes) pour JPEG et bruit, comme la métrique primaire de 1ter ; la géométrie reste hors périmètre.

## 5. Perturbations

Les perturbations restent photométriques (JPEG et bruit gaussien) et reprennent la structure de 1ter : tirages de développement avec trou autour des valeurs de validation, puis valeurs fixes pour la validation et la phase finale.

| Famille | Développement (tirages) | Validation (E) | Phase finale (C, F) |
| --- | --- | --- | --- |
| JPEG | qualité \~ U\[70 ; 90\], hors \[74 ; 76\] | qualité 75 | qualité 65 |
| Bruit gaussien | σ \~ U\[1 ; 2,4\], hors \[1,9 ; 2,1\] | σ = 2 | σ = 2,5 |

**K.** K = 50 tirages par famille (100 au total) pour estimer la robustesse des emplacements, comme dans le criblage de C-moyenne en 1ter ; K = 100 par famille est une analyse de sensibilité sur D-b, car un K plus grand durcit la règle et réduit le nombre d'emplacements robustes. Les mesures de décodage sur D-b utilisent une perturbation tirée par (couverture, message).

**Impact sur A2.** La phase finale est plus sévère que la validation, donc le nombre d'erreurs t par bloc y sera plus grand. Le budget de parité est jugé sur le nombre d'erreurs observé en validation, puis la phase finale révèle l'extrapolation, sans réglage.

**Graines et bibliothèques.** Une graine par source d'aléa (tirages, messages, bruit, partition, tirage des couvertures candidates de A4). Bibliothèques figées comme en 1ter ; Reed–Solomon par une bibliothèque fixée, dont la version est consignée au commit de gel. Un sous-ensemble est rejoué avec une seconde implémentation JPEG.

## 6. Métriques

La métrique primaire est le succès de communication : la fraction des tentatives où le message est exact après décodage Reed–Solomon, les tentatives infaisables comptant comme des échecs, sous JPEG 75 et bruit σ = 2.

| Métrique | Définition | Sert à |
| --- | --- | --- |
| d, d\_vide, d\_Hall | déficit d'affectation et sa décomposition (section 2) | Q1, H11 |
| Faisabilité | par message et conjointe sur les 12 messages, selon L_src ∈ {25 ; 50 ; 100 ; 200} octets | Q2 |
| Capacité | taille du couplage maximal sur emplacements robustes, par couverture | Q2 |
| Succès de communication | message exact après Reed–Solomon, sur toutes les tentatives | Q3, Q5, G-Q2 |
| Justesse de symbole | fraction d'octets exacts parmi les octets placés, et effective (échecs comptés comme erreurs) | continuité avec 1ter |
| Erreurs et effacements | e et t par bloc, marge de parité restante P_b − (e + 2t) | calibration de A2 |
| Bits par octet source | b\_assign (couche d'affectation, barrière) et b\_total (record complet), formules ci-dessous | G-Q2 |
| Indépendance (A4) | faisabilité observée sur m couvertures divisée par 1 − (1 − f)^m | H14 |

```latex
b_{\text{assign}} = \frac{N_{\text{placé}}\,b_{\text{fixe}} + L_{cw}}{L_{\text{src}}}, \qquad b_{\text{fixe}} = \lceil \log_2 M \rceil + \lceil \log_2 (2B+1) \rceil

b_{\text{total}} = \frac{8\,(F + Z_9)}{L_{\text{src}}}
```

N_placé est le nombre de symboles du mot code effectivement affectés à une position ; L_cw compte tous les symboles et donc tous les bits du bitmap, y compris les effacements. M est le nombre de positions. F = 41 octets est la surcharge fixe externe de l'enveloppe compacte FHAM (en-tête public 13, nonce 12, tag GCM 16). Z_9 est la longueur exacte après zlib-9 du record complet sérialisé de 1quater. Le corps est défini comme suit : en-tête interne `>4sBHHHI` (15 octets : magic, version, hauteur, largeur, taille de bloc, nombre de positions placées), identifiant de configuration (uint16 big-endian), L_src, L_c, L_cw et n_segments (uint16 big-endian chacun), CRC-32 (4 octets) de la source reconstruite, descripteur des segments, bitmap ⌈L_cw/8⌉, enregistrements des positions placées. Le config_id mappe 0-159 aux combinaisons p,q,m,B de la grille en ordre lexicographique et 160-319 aux mêmes combinaisons en mode A4 par segments source de 50 octets. Chaque entrée du descripteur contient L_src,i (uint8), L_c,i et L_cw,i (uint16 big-endian), puis son identifiant de couverture sur ceil(log2(m)) bits. Les sommes des longueurs par segment doivent retrouver L_src, L_c et L_cw. Les identifiants sont empaquetés MSB-first et le dernier octet est complété par des zéros. Le mode message entier a un segment. Le mode A4 segmente la source en blocs consécutifs de 50 octets au plus, compresse chaque segment indépendamment par zlib-9, puis applique RS. Dans chaque segment, les octets comprimés sont répartis déterministement en blocs source RS équilibrés de 128 octets au plus. Le bitmap est MSB-first (1 = effacement, 0 = placé) ; les enregistrements suivent l'ordre croissant des indices et contiennent token uint16 big-endian et déplacement int16 big-endian ; les identifiants sont codés sur ⌈log₂m⌉ bits par couverture, MSB-first, avec bourrage nul jusqu'à l'octet. Tous les champs du corps sont inclus dans Z_9, sans ajout séparé. b_total = 8(F + Z_9)/L_src. F a été mesuré sur l'enveloppe AES-GCM réelle ; Z_9 et b_total seront mesurés sur l'implémentation sérialiseur/protecteur de 1quater avant d'être rapportés. Le sérialiseur actuel `AuxiliaryChannel.protect` accepte uniquement un objet `Assignment` et ne sérialise pas encore le bitmap, le CRC ou les identifiants de galerie : son volume total ne doit donc pas être présenté comme b_total de 1quater. Le coût réseau, l'établissement de clé et la distribution de la galerie A4 sont hors métrique. Exemple sans effacement : L_src = 100, L_c = 111 (cas des octets uniformes), N_placé = L_cw = 134, p = 20 %, donc P = 23 : b_assign = 134 × 17 / 100 = 22,78 bits par octet source. À p = 30 % (P = 34), il vaut 24,65 et à p = 40 % (P = 45), 26,52. Pour ce message, ces deux cellules dépassent le seuil de 24 bits fixé pour G-Q2, qui s'applique à la moyenne à poids égal des 12 messages ; les familles sont aussi rapportées séparément.

**Mesure du sérialiseur.** `AuxiliaryChannel.protect` ajoute F = 41 octets fixes (en-tête public 13 + nonce 12 + tag AES-GCM 16). Le format direct ajoute 29 octets (en-tête 1 + nonce 12 + tag 16). L'en-tête sérialisé interne de 15 octets est inclus dans le plaintext zlib-9 ; seul, il se compresse à 21 octets, et le record vide protégé mesure 62 octets. Pour un record rempli, la contribution de cet en-tête est intégrée à Z_9. Le cadrage réseau, l'établissement de clé et la distribution de la galerie A4 restent hors métrique.

## 7. Statistiques et taille d'échantillon

Les méthodes sont celles de 1ter, avec la couverture comme unité statistique.

- **Intervalles.** Bootstrap par grappes sur les couvertures, 10 000 tirages, IC à 95 % par percentiles ; Wilson pour les taux de faisabilité.
- **Tests.** Permutation appariée par inversion de signe, 100 000 tirages, p = (1 + k) / 100 001, plus petit p atteignable ≈ 0,00001. Correction de Holm sur les trois hypothèses confirmatoires H12 à H14. H11 est descriptive et n'est pas testée.
- **Appariement.** Mêmes (couverture, message, perturbation) pour tous les leviers.
- **Tailles.** D-a : 100 ; D-b : 100 ; E : 200 ; F : 200 ; C : N = max(200, ⌈(1,96·sd\_Δ / 0,03)²⌉) avec sd\_Δ estimé sur D-b, de sorte qu'aucune observation de E ne sert à fixer la taille ni la configuration.
- **Seuil de réussite et taille.** Avec N = 200, la borne basse de Wilson atteint 0,92 à partir de 192 réussites sur 200 (96 %) ; avec 191 sur 200 (95,5 %), elle vaut 0,917. Un résultat de 95 % ne passerait donc pas la barrière verte de G-Q2 à cette taille.
- **Exploratoire contre confirmatoire.** Les étapes sur D sont exploratoires et toutes les cellules sont rapportées. La configuration est gelée avant E ; E, puis C et F, sont des passages uniques.
- **Indépendance dans A4.** Les m couvertures d'un tirage partagent des tirages de perturbation ; le bootstrap rééchantillonne le pool de couvertures et retire les sous-ensembles ; le rapport d'indépendance (section 6) est rapporté, jamais présumé.

## 8. Procédure et budget

La procédure est séquentielle, avec une barrière à chaque étape ; la règle de choix de la configuration est gelée avant toute mesure sur E.

| Étape | Contenu | Jeu | Sortie |
| --- | --- | --- | --- |
| 0 | gel, commit, manifestes, version de la bibliothèque Reed–Solomon | — | hash du commit |
| 1 | diagnostics D1 à D5 (section 2) | D-a | G-Q0 |
| 2 | A1 : faisabilité et capacité en fonction de n | D-b | G-Q1 |
| 3 | A2 : effacements et parité p ∈ {10 ; 20 ; 30 ; 40 %} ; B ∈ {4 ; 8} | D-b | tableau de frontière |
| 4 | A3 : fraction non robuste q ∈ {0 ; 2 ; 5 ; 10 %} | D-b | tableau de frontière |
| 5 | A4 : m ∈ {1 ; 2 ; 3 ; 5} ; blocs de 50 octets | D-b | tableau de frontière, rapport d'indépendance |
| 6 | choix parmi les 160 cellules : la plus petite valeur de b\_assign (moyenne sur les 12 messages) avec un succès ≥ 0,95 sur D-b ; égalité : plus petit p, puis plus petit q, puis plus petit m, puis plus petit B | D-b | G-Q2, configuration gelée |
| 7 | validation, un seul passage | E | G-Q3 |
| 8 | phase finale, un seul passage par corpus | C et F | G-Q4 |

**Budget de calcul (estimations, non mesurées).** Elles reposent sur 0,43 s par codebook (profil 12 × 12, mesuré avant 1ter ; à remesurer sur 5 couvertures) et 100 tirages par couverture (K = 50 par famille).

- D-b : 100 × 100 × 0,43 s ≈ 1,2 h pour estimer la robustesse, plus environ 17 min de recalcul des hachages perturbés (12 messages × 2 canaux × 100 couvertures × 0,43 s) ; l'affectation et le décodage Reed–Solomon des 160 cellules sont supposés négligeables (à confirmer par mesure).
- E : 200 × 100 × 0,43 s ≈ 2,4 h.
- C : N ≥ 200 couvertures, environ 2,4 h à N = 200.
- F : le coût est censé croître avec le nombre de positions, soit environ quatre fois (1,72 s par codebook) : 200 × 100 × 1,72 s ≈ 9,6 h. Une mesure sur 5 couvertures remplace cette estimation avant l'étape 8.

1ter a tourné plus vite que mes estimations précédentes ; ces chiffres sont des plafonds.

**Points d'arrêt.** Arrêt à la fin d'une étape si sa barrière n'est pas verte. Aucune étape ne dépasse E avant G-Q2, et aucune n'ouvre C ou F avant G-Q3.

## 9. Barrières G-Q0 à G-Q4 et feux

Chaque seuil est fixé avant exécution ; un écart de seuil après coup est consigné comme post hoc.

| Barrière | Verte | Orange | Rouge |
| --- | --- | --- | --- |
| G-Q0, préalables (descriptive) | D1 à D7 produits ; rejeu exact des étiquettes de 1ter (7 200 sur 7 200 atteint) | — | rejeu inexact : corriger avant tout |
| G-Q1, capacité (A1, descriptive) | courbe de faisabilité par message produite ; L_src* est le plus grand L_src ∈ {25 ; 50 ; 100 ; 200} dont la borne basse de Wilson est ≥ 0,90. Rapporter séparément L_src* pour chacun des 12 messages et pour l'événement conjoint « les 12 sont faisables » ; « non atteint » si aucune taille ne passe, « ≥ 200 » si 200 passe | — | — |
| G-Q2, développement (D-b) | une cellule parmi les 160 avec succès ≥ 0,95 (estimation) et b\_assign moyen ≤ 24 | succès ≥ 0,90 et < 0,95, ou b\_assign > 24 et ≤ 28 : E n'est pas ouvert | succès < 0,90 ou b\_assign > 28 : arrêt, limite documentée |
| G-Q3, validation (E) | succès ≥ 0,96 sur chaque canal (JPEG 75, bruit σ = 2), soit une borne basse de Wilson ≥ 0,92 à N = 200 | une seule des deux familles passe | aucune ne passe |
| G-Q4, phase finale (C et F) | borne basse ≥ 0,92 sur C et sur F à la sévérité de validation | vert sur un seul corpus, ou écart entre corpus > 0,05 | rouge sur les deux |

Les résultats à la sévérité du jeu scellé (JPEG 65, σ = 2,5) sont rapportés comme extrapolation et ne portent aucune barrière.

**Suites.**

- **G-Q4 vert :** rédiger le protocole de géométrie et de sécurité de bout en bout.
- **G-Q4 orange :** expliquer l'écart entre corpus avant d'aller plus loin.
- **Rouge à toute barrière :** documenter la limite ; le mode catalogue (univers fermé) reste le mode supporté.

## 10. Menaces à la validité et replis

| Menace | Parade |
| --- | --- |
| Malédiction du vainqueur : la meilleure cellule d'une grille de leviers est optimiste | règle de choix gelée (section 8), puis un seul passage sur E, C et F |
| D-a déjà exploitée par 1ter | D-a ne sert qu'à G-Q0 ; D-b et E servent à décider |
| D-b supposée jamais traitée | vérifier dans les manifestes de 1ter avant le gel |
| Indépendance des couvertures dans A4 | rapport d'indépendance et bootstrap par couvertures ; jamais de produit de probabilités présenté comme garantie |
| Mauvaise correction Reed–Solomon au-delà de la capacité | le succès exige l'égalité exacte des octets ; en usage réel, un contrôle d'intégrité (par exemple 4 octets de CRC-32) s'ajoute et se compte dans b\_source |
| Précision des messages comprimés | messages zlib-9 proches d'octets uniformes, le cas le plus défavorable pour la couverture des valeurs ; familles séparées dans les rapports |
| Seuil de 24 bits par octet source | choix de conception, rapporté avec la frontière complète pour que le lecteur juge |
| Non-transfert entre corpus | A5 mesuré séparément, sans réglage ; aucune extrapolation de BOWS2 à BOSSBase |
| Sécurité : l'affectation partielle, le bitmap d'effacement et le choix de couverture changent les statistiques du record | hors périmètre ici ; à examiner dans le protocole de sécurité avant toute revendication de indétectabilité |
| Effets de bibliothèque (JPEG, Reed–Solomon) | versions figées ; sous-ensemble rejoué avec une seconde implémentation JPEG |

**Règles posées après un résultat.** La règle de décision de A2 (G-Q0 descriptive) a été fixée après le diagnostic post hoc ; elle élargit l'évaluation et ne retient aucune branche. Le seuil de 24 bits (maintenu tel quel, fixé avant la grille et non modifiable après) et la grille de 160 cellules sont aussi des choix de conception, et une grille large sur 100 couvertures accroît le risque de maximum optimiste, d'où la validation sur E.

**Replis.** Si G-Q2 est rouge, les trois leviers ne suffisent pas à lever le plafond de capacité : l'article présente alors le mode catalogue (univers fermé) comme mode supporté, avec les deux métriques côte à côte (justesse conditionnelle et succès de communication) et les limites mesurées. Chaque levier est jugé sur ses propres mesures de D-b, non sur G-Q0.

## 11. Livrables

**Fichiers.** Un CSV par ligne (couverture, message, perturbation, levier), qui reprend le schéma de 1ter et ajoute : n, B, p, q, m, d, d\_vide, d\_Hall, faisable, effacements e, erreurs t, succès, b\_source, corpus. Manifestes SHA-256 des jeux, hash du commit, versions des bibliothèques, graines.

| Tableau | Contenu |
| --- | --- |
| T1 | distribution du déficit d et de sa décomposition (G-Q0) |
| T2 | faisabilité et capacité en fonction de n (A1) |
| T3 | A2 : succès, e, t et b\_source par p et par B |
| T4 | A3 : faisabilité et justesse conditionnelle par q |
| T5 | A4 : faisabilité par m, et rapport d'indépendance |
| T6 | frontière succès contre b\_source, toutes les cellules |
| T7 | validation sur E, phase finale sur C et F, avec IC |

**Figures.** Histogramme du déficit ; courbe de faisabilité en fonction de n ; frontière succès contre b\_source.

**Page de décision.** Une page : feux G-Q0 à G-Q4, configuration retenue, écarts avec ce protocole classés comme post hoc, et suite recommandée.
