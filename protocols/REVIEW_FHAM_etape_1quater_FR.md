# Audit du protocole 1quater corrigé

**État :** lecture complète de `FHAM — Protocole de l'étape 1quater déficit d'affectation, effacements et repli(1).md` (18 novembre 2026). Les corrections proposées dans les dix points précédents sont présentes pour l’essentiel. Le fichier de Downloads n’a pas été modifié depuis ce dépôt. G-Q0, D6 et D7 sont des diagnostics post hoc sur D-a; aucune cellule A1–A5 n’a été lancée.

## Corrections vérifiées

- G-Q0 est explicitement descriptif et ne choisit plus de branche; G-Q2 décide sur D-b.
- Les longueurs source, comprimée et codée sont distinguées; le CRC reste dans le record.
- Les mots RS sont segmentés en blocs équilibrés de 128 symboles maximum, sous la limite GF(256).
- G-Q1 rapporte n* par message et pour la conjonction des 12 cas. Comme la mesure est explicitement descriptive, aucun seuil d’acceptation additionnel n’est nécessaire; écrire que n* est calculé parmi les quatre longueurs testées (25, 50, 100, 200) et « non atteint » si aucune ne satisfait la borne basse de Wilson 0,90.
- K=50 par famille correspond bien au criblage C-moyenne 1ter; K=100 est une sensibilité prévue sur D-b.
- Les messages de 25 octets sont définis comme préfixes des messages de 50 octets avec empreintes à geler.
- La grille de 160 cellules et sa règle de choix sont explicitement données.
- b_assign est séparé de b_total; D-b sert à estimer la taille N; la sécurité complète est hors périmètre et reste à traiter ailleurs dans l’article.

## Points résiduels avant gel

1. **D6 : utiliser la parité réelle pour la borne.** Le brouillon propose des octets pseudo-aléatoires pour étendre le mot. C’est un proxy utile pour une sensibilité, mais `d≤P` n’est une condition nécessaire sur le succès par effacements que si le déficit est calculé sur le mot RS effectivement encodé. Le diagnostic exécuté ci-joint utilise les deux : le proxy aléatoire et les mots exacts générés par `reedsolo` 1.7.0. Pour D6, retenir la parité RS exacte comme résultat principal et conserver le proxy comme comparaison exploratoire.
2. **Seuil de préfiltrage D6.** Le brouillon dit qu’une fraction `d≤P` sous 0,90 exclut le passage de G-Q2, dont la réussite minimale est 0,95. C’est une condition suffisante pour écarter A2 seul, mais une fraction entre 0,90 et 0,95 l’écarte aussi sur ce critère, si la borne est interprétée sur la même moyenne de messages. À préciser avant de décider du calcul A2 seul; les interactions A3/A4 peuvent encore changer la conclusion.
3. **D7 et portée du diagnostic.** La surcharge d’une valeur x dans sa fenêtre ±B est un témoin Hall suffisant pour un symbole seul, mais son absence n’établit pas la faisabilité : les fenêtres de plusieurs valeurs peuvent se recouvrir. Le rapport D7 distingue les surcharges unitaires des déficits qui n’apparaissent qu’en combinant plusieurs valeurs.
4. **Définition de F dans b_total.** La formule utilise `F+4+2`; le texte définit F à la fois comme partie fixe comprenant le CRC et la longueur, et comme 29 octets de format/nonce/tag. Dire explicitement si F exclut les 4 octets de CRC et les 2 de longueur. Résoudre aussi l’écart 29/41 octets avant d’interpréter b_total. La porte de 24 bits porte sur b_assign et n’est pas affectée, mais b_total ne doit pas rester ambigu.
5. **Périmètre de la moyenne à G-Q2.** Le texte indique moyenne des 12 messages et tableaux par famille; conserver également les quatre moyennes de famille et les bornes individuelles pour éviter qu’une famille très compressible ne masque un coût ou un échec plus élevé dans une autre.
6. **A4 prépartagé.** L’hypothèse de galerie prépartagée est maintenant explicite. Le coût d’acquisition/distribution de la galerie reste hors b_total; garder A4 qualifié comme mode catalogue et ne pas présenter cette mesure comme un coût complet de communication pour une galerie non partagée.

## Résultats D6/D7 à annexer au protocole

- **D6, RS exact, C-moyenne, B=8, D-a :** les fractions de cas où `d≤P` sont 81,3 %, 87,3 %, 90,2 %, 92,1 % et 92,5 % pour p=0, 10, 20, 30 et 40 %. Avec le seuil G-Q2 de 95 %, même p=40 ne laisse que 92,5 % de cas potentiellement récupérables sous canal parfait dans D-a. C’est une borne de filtrage descriptive sur D-a, pas une décision confirmatoire sur D-b. B=4 atteint 89,2 % à p=40.
- **D6, familles à B=8/p=40 :** octets uniformes 90,7 %, ASCII 89,3 %, texte naturel 91,3 %, octet répété 98,7 %. La moyenne sur 12 messages est 92,5 %.
- **D7 :** l’entropie des hashes robustes est en moyenne 6,760 bits contre 7,395 sur toutes les positions; support effectif 119,9 contre 171,8; part dans les dix valeurs dominantes 21,8 % contre 17,1 %. Cela confirme une concentration statistique associée à la sélection robuste, sans prouver qu’elle explique à elle seule les déficits.
- **D7 à B=8 :** 142/224 messages infaisables ont une surcharge de fenêtre pour une valeur seule; 82 ont un résidu de Hall sans surcharge unitaire, compatible avec des collisions entre fenêtres de valeurs différentes.

Le calcul détaillé et ses limites figurent dans `results/stability_step1/step1ter/audit_diagnostics/GQ0_posthoc/REPORT_D6_D7_FR.md`.

## Statut recommandé

Le texte révisé est proche d’un gel, mais le point F/b_total doit être clarifié et la règle D6 doit distinguer parité RS exacte du proxy aléatoire. Une fois ces retouches réalisées, figer le protocole et les manifestes D-b par hash, puis arrêter avant toute cellule si une précondition ou un budget mesuré ne correspond pas au document. Les résultats de sécurité de bout en bout, association image–record, rejeu, établissement des clés et détectabilité réseau restent des tâches séparées liées aux reviewers.
