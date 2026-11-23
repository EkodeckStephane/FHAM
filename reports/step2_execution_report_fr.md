# Étape 2 FHAM — compte rendu d’exécution

**Date :** 21 novembre 2026
**Branche :** `revision/step2-end-to-end-2026-11-21`
**Protocole gelé :** commit `a4775ee`; addendum v1.2. Le SHA-256 du document source, vérifié au gel, est `BE2FD2D16C5FFB366ABEBECD92B15B3FC53552550A1147DED66264DE305EA061`. Les mesures de 1quater sont restées en lecture seule.

## Résumé des conclusions

1. **Sécurité des records : progrès substantiel dans le modèle testé.** Le profil V1 lie le record à la galerie ordonnée et aux paramètres, protège le contenu par AEAD et par un contrôle d’intégrité du message, et utilise un échange X25519 éphémère signé. Toutes les mutations testées ont été rejetées. Cela ne constitue pas une preuve formelle ni une validation de déploiement.
2. **Détectabilité : échec net pour les profils mesurés.** En observation locale appariée, l’AUC test vaut 1,00 pour R0 et R1 en TCP direct comme en TLS 1.3. Une comparaison secondaire avec les traces TLS NonVPN existantes donne également AUC 1,00 pour R0/R1. Cela démontre une détectabilité par les signaux mesurés dans ces conditions ; cela ne permet pas de généraliser à tout réseau ou adversaire.
3. **Synchronisation géométrique : limite non levée.** Sur D-b, avec la transformation inverse exacte, le succès exact est de 1,81 % pour le recadrage, 12,66 % pour la rotation et 94,57 % pour le redimensionnement-restauration. Le goulot est la stabilité du descripteur après rééchantillonnage, pas seulement l’estimation du mouvement. Conformément au point d’arrêt G-2, aucune validation E-geo ni recherche P4 n’a été lancée ; C-geo et F-geo restent scellés.

## S — sécurité du format V1

Le format mesuré utilise un catalogue ordonné prépartagé, un digest de catalogue dans les données associées AEAD, des paramètres de protocole liés au transcript, un échange X25519 signé par Ed25519, une dérivation HKDF à clés directionnelles, confirmations de clé et un digest SHA-256 tronqué à 128 bits (I1) dans le contenu authentifié. Le récepteur vérifie le catalogue, I1 et la séquence avant de faire avancer l’état de rejeu.

| Mesure | Résultat |
| --- | ---: |
| Classes de mutation V1 | 18 × 1 000 essais, 0 acceptation |
| Classes legacy V0 | 11 × 1 000 essais, 0 acceptation dans les vérifications applicables |
| Basculements d’un bit sur les records | 58 880/58 880 rejetés |
| Altérations de message I1 | 20 000/20 000 rejetées |
| Tests de redémarrage et de rollback | 1 000 essais, aucune continuité rompue ni ancien snapshot accepté avec l’époque monotone de confiance fournie au test |
| Handshake applicatif V1 | 338 octets mesurés (2 offres de 127 et 2 confirmations de 42 octets, framing inclus) |
| Secret rétrospectif | les records capturés ne sont pas déchiffrables après révélation de la clé d’identité ; clés de session liées au contexte et séparées par direction |

Le résultat de rejeu après rollback dépend d’une source d’époque monotone de confiance externe : SQLite seul ne protège pas contre la restauration d’un snapshot. La distribution, la rotation et la révocation des identités et du catalogue n’ont pas été évaluées. L’effacement physique des clés n’est pas revendiqué dans l’implémentation Python. Aucun modèle formel ProVerif n’a été exécuté.

R1 fixe le record applicatif à 406 octets. Cette taille fixe ne signifie ni faible coût ni indétectabilité : la distribution du catalogue est hors record, et le handshake ainsi que le flux complet restent observables.

## D — longueur et détectabilité réseau

### Longueur des records

Sur 8 000 records équilibrés par famille, le classifieur groupé par contenu atteint 71,79 % d’exactitude à quatre classes pour R0, contre 25 % au hasard ; l’information mutuelle est de 1,306 bit. Pour R1, l’exactitude est 24,96 % et l’information mutuelle mesurée est nulle. R1 masque donc la famille à partir de la seule longueur de record dans cet échantillon.

Le remplissage a un coût. La taille moyenne du record complet est de 406 octets pour R1. Pour R0, les moyennes sont de 157,6 octets (répétitif), 381,9 (texte naturel), 383,4 (ASCII imprimable) et 392,6 (octets uniformes). Le record AES-GCM direct de 100 octets occupe 128 octets sans compression. Avec zlib-9 avant AES-GCM, les références moyennes vont de 40,0 à 139,0 octets. R0/R1 restent donc plus volumineux que la référence directe pour les quatre familles, surtout après compression directe.

### Flux TCP/TLS 1.3 générés avec le récepteur réel

L’expérience complète comporte 1 600 sessions positives et 1 600 contrôles par condition, cinq records par session : 12 800 flux sur TCP-R0, TCP-R1, TLS 1.3-R0 et TLS 1.3-R1. Les 12 800 sessions ont été acceptées et reconstruites exactement côté récepteur. Les partitions gelées comptent 400 sessions d’entraînement, 200 de validation et 1 000 de test par classe et condition.

| Condition | Observables utilisés | AUC test | IC bootstrap groupé à 95 % | Balanced accuracy au seuil gelé sur validation |
| --- | --- | ---: | ---: | ---: |
| TCP-R0 | marqueur applicatif visible et volumes directionnels | 1,00 | [1,00 ; 1,00] | 1,00 |
| TCP-R1 | marqueur applicatif visible et volumes directionnels | 1,00 | [1,00 ; 1,00] | 1,00 |
| TLS 1.3-R0 | tailles/nombres de records TLS et volumes directionnels | 1,00 | [1,00 ; 1,00] | 1,00 |
| TLS 1.3-R1 | tailles/nombres de records TLS et volumes directionnels | 1,00 | [1,00 ; 1,00] | 1,00 |

Les contrôles utilisent les mêmes cinq messages source que leur flux FHAM apparié, dans une connexion TCP ou TLS locale. La comparaison isole donc le coût et la forme du protocole mesuré, mais ne représente pas à elle seule le trafic ordinaire d’Internet.

### Référence NonVPN externe

Les archives `NonVPN-PCAPs-01/02/03.zip` ont été lues sans extraction ni écriture sur `D:\dataset`. Le manifeste vérifie que les 91 captures utilisées dans le tableau de caractéristiques correspondent chacune à un membre unique des 109 PCAP/PCAPNG des archives. Les tailles et CRC-32 des membres, les empreintes SHA-256 des archives, des caractéristiques et des scripts d’extraction sont consignés dans `results/step2/detection/nonvpn_reference_provenance.json`. Les captures n’ont pas été décompressées et reparsées pendant cet audit ; la provenance s’appuie sur les empreintes des archives et du résultat déjà extrait.

Les partitions sont disjointes par fichier de capture (63 entraînement, 14 validation, 14 test). Le test compare 1 000 flux TLS FHAM à 254 flux TLS NonVPN répartis sur 14 captures. L’AUC test est 1,00 pour R0 et R1, avec une borne bootstrap groupée inférieure à 1,00 uniquement à l’arrondi machine près. Ce contraste est très fort dans ce corpus, mais l’âge des captures, les applications et les environnements diffèrent ; il ne constitue pas une estimation universelle du taux de détection.

**Écart au protocole :** PktMon ne fournit pas de composant loopback sur cette machine ; son PCAP pilote est vide. Une tentative de capture ETW alternative a demandé une élévation administrative qui n’a pas abouti. Les mesures FHAM locales utilisent donc les écritures/lectures des vrais sockets et les longueurs des records TLS 1.3 observées dans les BIO TLS. Les longueurs des appels de fonctions locales ne sont pas utilisées comme tailles de paquets. Aucun résultat n’est présenté comme une analyse PCAP des paquets FHAM, et aucune revendication d’indétectabilité n’est permise.

Le filtre PktMon créé pour l’essai a été arrêté, mais Windows a refusé sa suppression sans privilèges administrateur ; il reste configuré mais inactif. Il devra être retiré par un administrateur (`pktmon filter remove`).

## G — synchronisation géométrique

Les résultats D-b agrègent 387 tentatives A4, deux segments par message et 96 images catalogue distinctes. ORB/RANSAC produit un recalage pour toutes les images transformées testées ; ce succès de recalage ne donne pas la récupération exacte.

| Transformation | P1 coordonnées fixes | P2 ORB/RANSAC | P3 inverse géométrique exact |
| --- | ---: | ---: | ---: |
| Recadrage-restauration | 0,00 % | 0,78 % | 1,81 % (IC bootstrap groupes couverture : [0,00 ; 4,70] %) |
| Rotation | 0,26 % | 10,85 % | 12,66 % (IC : [7,03 ; 19,08] %) |
| Réduction-restauration | 94,57 % | 92,76 % | 94,57 % (IC : [89,97 ; 98,15] %) |

La transformation exacte ne sauve pas la récupération après recadrage ou rotation. La grille P4 et les jeux E-geo/C-geo/F-geo n’ont donc pas été ouverts : poursuivre l’optimisation d’une recherche de transformation ne peut lever le plafond déjà observé quand cette transformation est connue. La synchronisation géométrique reste une limite du profil courant.

## Écarts et limites à conserver dans l’article

- La sécurité V1 est une évaluation expérimentale ciblée, pas une preuve formelle ni une certification de protocole.
- La protection contre le rollback suppose une source d’époque monotone externe ; la distribution des clés et du catalogue reste à spécifier pour un déploiement.
- Les records sont détectables dans les expériences locales et dans la comparaison TLS NonVPN. L’observation locale n’est pas une capture de paquets ; le corpus externe est historique et limité à 254 flux de test répartis sur 14 captures.
- Les résultats géométriques ne valident que les transformations et images D-b mesurées. Rotation et recadrage échouent même sous inverse oracle ; aucune robustesse générale ne peut être affirmée.
- La détection de pixels n’est pas évaluée, puisque les couvertures ne sont pas modifiées.
- Le système mesuré repose sur une galerie de couvertures prépartagée, deux couvertures candidates par segment et des métadonnées. Son coût excède le chiffrement direct dans les familles mesurées.

## Artefacts principaux

- `src/fham/v1.py` — format, handshake, AEAD, contrôle I1 et rejeu.
- `tests/test_v1_protocol.py` — tests ciblés du format V1.
- `scripts/run_step2_security.py` — tests S.
- `scripts/run_step2_network_capture.py` — génération de flux V1 et validation réelle par récepteur ; instrumentation d’extrémité, pas capture de paquets.
- `scripts/analyze_step2_endpoint_detectability.py` et `scripts/analyze_step2_tls_reference_detectability.py` — classifieurs D.
- `scripts/audit_step2_nonvpn_reference.py` — empreintes et correspondances d’archives.
- `scripts/run_step2_geometry_development.py` et `scripts/summarize_step2_geometry_development.py` — mesures G sur D-b.
- `results/step2/security/`, `results/step2/detection/` et `results/step2/geometry/` — données, résumés et manifestes.

## Addendum du 23 novembre 2026 — extension P4 post hoc sur E-geo

Le point d’arrêt G-2 ci-dessus décrit la décision prise après l’analyse initiale de D-b. À la demande de l’auteur, une extension exploratoire P4 a ensuite été menée séparément sur D-b, puis sur E-geo selon le protocole post hoc `protocols/FHAM_etape_2_extension_posthoc_P4_sealed_2026-11-21.md`. Ces mesures ne sont pas confirmatoires et ne modifient pas rétrospectivement le protocole v1.2.

Le passage E-geo terminé le 23 novembre donne une borne basse bootstrap de 0,8198 pour le redimensionnement-restauration, de 0,0867 pour la rotation et de 0 pour le recadrage-restauration. Une seule des trois familles géométriques atteint le seuil G-G2 (borne basse ≥ 0,80). Le verdict est **orange**. C-geo a été ouvert avant que le garde-fou orange soit visible dans le runner. Une reprise a ensuite produit 200 codebooks, quatre archives d’affectation et 14 tentatives partielles; ces données sont exclues de toute estimation P4. Le point d’arrêt est désormais appliqué : C-geo ne sera pas relancé et F-geo reste fermé. Les artefacts sont conservés dans `results/step2/geometry/p4_C_geo_*`; les incidents et l’état réel des fichiers sont consignés dans `results/step2/geometry/p4_C_geo_incidents.json`.
