# Résultats de l’étape 1quater — FHAM

**Date : 21 novembre 2026**

**Protocole :** `FHAM_etape_1quater_preregistre.md`, complété avant l’ouverture de C/F par `FHAM_etape_1quater_clarification_preouverture_C_F_2026-11-21.md`.

**Configuration figée avant E :** `p=10 %`, `q=5 %`, `m=2`, `B=4`, `config_id=50`, profil de hachage L=12.

**Échantillons finaux :** E et C, 200 images BOWS2 natives 256×256 chacun; F, 200 images BOSSBase natives 512×512. Chaque corpus a été mesuré une fois, pour 12 messages de 100 octets et 200 tirages de galerie par message.

## Décision des barrières

| Barrière | Résultat | Décision |
| --- | --- | --- |
| G-Q1 — capacité descriptive | Courbes produites pour 25, 50, 100 et 200 octets; aucune taille conjointe ne passe la borne de faisabilité prévue pour les 12 messages. | Résultat descriptif conservé. |
| G-Q2 — développement D-b | Configuration 50 : succès moyen 96,17 % JPEG et 96,33 % bruit; coût d’affectation moyen 14,12 bits/octet source, inférieur au plafond de 24. | **Vert**, configuration gelée. |
| G-Q3 — validation E | Succès macro 97,04 % JPEG et 97,46 % bruit. IC bootstrap par couvertures à 95 % : [95,83; 98,54] % et [95,75; 98,38] %. | **Vert**, C/F autorisés. |
| G-Q4 — phase finale C/F | Les bornes basses des IC bootstrap par couvertures sont au moins 92 % sur les deux corpus et canaux. Écarts ponctuels F−C : 4,04 points JPEG et 4,21 points bruit, sous le seuil de 5 points. | **Vert selon le critère préenregistré d’IC par couverture et d’écart ponctuel.** |

Les intervalles bootstrap rééchantillonnent 10 000 fois les couvertures et retirent à chaque tirage deux candidates de galerie. Les bornes Wilson calculées à partir du taux macro arrondi à 200 observations sont également rapportées comme diagnostic : elles passent pour F et E, mais pas pour C. Elles ne remplacent pas l’intervalle par couvertures, l’unité statistique définie par le protocole. Cette différence de lecture doit rester visible dans toute présentation des résultats.

## Résultats par corpus

| Corpus | Succès JPEG 75 | IC bootstrap 95 % | Succès bruit σ=2 | IC bootstrap 95 % | Faisabilité moyenne | Coût d’affectation | Taille totale FHAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| E — BOWS2, validation | 97,04 % | [95,83; 98,54] % | 97,46 % | [95,75; 98,38] % | — | 14,12 bits/octet (config évaluée) | 26,19 bits/octet (config évaluée) |
| C — BOWS2, phase finale | 94,71 % | [92,71; 97,13] % | 94,00 % | [92,33; 96,63] % | 96,46 % | 14,12 bits/octet | 26,14 bits/octet |
| F — BOSSBase 512×512 | 98,75 % | [97,75; 99,54] % | 98,21 % | [96,83; 99,08] % | 98,97 % | 16,00 bits/octet | 27,16 bits/octet |

La moyenne macro de C masque une dispersion entre messages : les minima sont de 85,5 % en JPEG et 82,0 % sous bruit, contre 97,0 % et 96,0 % sur F. Sur C, la famille ASCII imprimable est la plus faible (moyennes de 89,3 % et 88,2 %); les messages octet répété atteignent 99,3 % sur les deux canaux. Ces valeurs confirment que la distribution du message et la couverture des valeurs par le dictionnaire modulent le succès.

La différence ponctuelle entre F et C reste sous 5 points, mais son IC bootstrap indépendant inclut des écarts supérieurs à 5 points : [1,42; 6,21] points en JPEG et [1,13; 6,00] points sous bruit. Les données sont donc compatibles avec une différence de corpus potentiellement supérieure au seuil, malgré le passage de G-Q4 selon les critères ponctuels gelés. La généralisation entre corpus doit être formulée avec cette réserve.

## Coût de communication

La comparaison de référence pour un message de 100 octets est 129 octets sous AES-GCM direct (10,32 bits par octet source). Le record FHAM complet, avec enveloppe protégée, atteint environ 327 octets en moyenne sur C (26,14 bits/octet) et 340 octets sur F (27,16 bits/octet). FHAM n’améliore donc pas le volume face au chiffrement direct dans ce protocole.

Le coût dépend fortement du message. Sur C, le coût total moyen par famille va d’environ 10,18 bits/octet pour les messages répétés à 33,08 pour les octets uniformes; sur F, de 10,37 à 34,59. La compression de l’enveloppe profite beaucoup aux messages répétitifs, tandis que les records de messages plus riches paient les jetons de position, les résidus, l’effacement et les champs fixes. Le plafond d’affectation `b_assign` n’inclut pas toute l’enveloppe; il ne doit pas être présenté comme la taille réelle transmise.

## Éléments positifs établis

- La configuration choisie sur D-b conserve son niveau de récupération sur E, puis atteint des bornes bootstrap supérieures à 92 % sur BOWS2-C et BOSSBase-F pour JPEG et bruit.
- Le résultat se transfère à un second corpus et à une résolution native de 512×512, pour cette configuration précise.
- L’affectation partielle avec Reed–Solomon et le choix parmi deux couvertures sont compatibles avec une récupération complète élevée sous les deux perturbations évaluées.
- Les enregistrements indiquent explicitement l’infaisabilité; la faisabilité de l’affectation reste distincte de la récupération exacte après perturbation.

## Limites et risques scientifiques qui restent ouverts

1. **Coût du record.** Pour les messages généraux mesurés, le record complet reste environ 2,5 à 2,6 fois plus gros que le message protégé directement par AES-GCM. La contribution ne peut pas être défendue comme un gain de volume de communication.
2. **Capacité dépendante du contenu.** Les résultats d’A1 et les différences entre familles interdisent une capacité annoncée par le seul nombre de positions; la distribution et les multiplicités des valeurs affectent la faisabilité de Hall.
3. **Sécurité de la chaîne complète.** 1quater n’évalue ni l’établissement de clé, ni le rejeu, ni l’association cryptographique de l’enveloppe à l’image, ni la détection de FHAM dans du trafic ordinaire. Le présent résultat ne lève pas les critiques de sécurité des reviewers.
4. **Détectabilité réseau et sécurité stéganographique.** Les expériences de récupération sous JPEG/bruit ne constituent pas une évaluation de stéganalyse ou de trafic TLS. Aucune revendication d’indétectabilité ne découle de 1quater.
5. **Géométrie.** Les tests finaux concernent JPEG et bruit. Ils ne résolvent pas la synchronisation sous rotation, recadrage ou changement d’échelle; la récupération exacte après transformation géométrique reste une limite.
6. **Paramètres.** C, F et E valident un seul profil et une configuration sélectionnée sur D-b. La généralisation de `p`, `q`, `m`, `B`, du descripteur et de la résolution reste à étudier.
7. **Incertitude corpus.** Les IC du contraste F−C chevauchent des écarts de 5 points ou plus; la différence entre corpus demande une interprétation prudente.

## Portée vis-à-vis des reviewers

Les résultats renforcent la réponse sur la distinction entre faisabilité et récupération, la relation entre distributions de messages et faisabilité, ainsi que l’évaluation de la configuration sur des données de validation et un corpus séparé. Ils apportent une mesure reproductible du coût total, qui confirme une limite plutôt qu’un avantage face à AES direct.

Ils ne suffisent pas à justifier à eux seuls la contribution face à AES-GCM direct, à définir un protocole de communication complet, à évaluer la sécurité de bout en bout, à établir l’indétectabilité du trafic ou à résoudre la synchronisation géométrique. La motivation scientifique devra défendre la contribution comme une couche d’affectation bornée et optimisée, tout en délimitant nettement ses responsabilités et ses coûts.

La réponse aux reviewers, la cover letter et le tracked-changes document restent à produire après l’achèvement de la révision intégrale du manuscrit, afin que les formulations correspondent aux résultats finaux.

## Artefacts et reproductibilité

- Gel G-Q2 : `results/stability_step1/step1quater/run/GQ2_configuration_freeze.json`.
- Clarification et gel avant C/F : `protocols/FHAM_etape_1quater_clarification_preouverture_C_F_2026-11-21.md` et `results/stability_step1/step1quater/run/final_freeze/`.
- G-Q3 : `results/stability_step1/step1quater/run/E_validation/GQ3_gate.json`.
- G-Q4 : `results/stability_step1/step1quater/run/GQ4_decision.json`, résultats détaillés C/F dans leurs sous-répertoires respectifs.
- Scripts d’exécution, de bootstrap et de traçabilité : `scripts/run_step1quater_final_corpus.py`, `scripts/bootstrap_step1quater_final.py`, `scripts/prepare_step1quater_final_freeze.py`.
