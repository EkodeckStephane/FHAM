# Clarification préouverture de 1quater : définition de Δ et gel des manifestes C/F

**Date : 21 novembre 2026.** Cette note complète le protocole `FHAM_etape_1quater_preregistre.md` après le passage vert de G-Q3 et avant toute ouverture des pixels C ou F. Elle ne modifie ni la configuration choisie ni les critères de G-Q4.

## Définition opérationnelle de `sd_Δ`

La formule de taille d'échantillon pour C utilisait `sd_Δ` sans définir Δ. Pour rendre le calcul reproductible, Δ désigne ici le taux de récupération exacte par couverture source, calculé séparément pour les deux canaux gelés (JPEG 75 et bruit σ = 2), sur les 12 messages de 100 octets et les tentatives de galerie disponibles dans D-b pour la configuration gelée `p=10 %, q=5 %, m=2, B=4`.

Pour chaque canal, on calcule d'abord le taux de succès de chaque couverture source effectivement sélectionnée dans les tentatives D-b. `sd_Δ` est l'écart-type d'échantillon entre ces taux, avec `ddof=1`. La valeur la plus élevée parmi les deux canaux sert au calcul :

\[
N_C=\max\left(200,\left\lceil\left(\frac{1.96\,\max(sd_{\Delta,JPEG},sd_{\Delta,bruit})}{0.03}\right)^2\right\rceil\right).
\]

Ce choix dimensionne C pour une demi-largeur nominale de 0,03 sur le taux moyen de chaque canal, avec une unité d'échantillonnage égale à la couverture. La borne minimale de 200 et le seuil G-Q4 (borne basse de Wilson ≥ 0,92) restent inchangés. Cette clarification exploite uniquement les sorties D-b; aucune mesure E n'entre dans le calcul.

Résultat D-b : `sd_Δ,JPEG = 0,117043`, `sd_Δ,bruit = 0,068190`; les deux formules donnent un effectif inférieur à 200. **N_C est donc fixé à 200.**

## Manifestes gelés

- **C :** 200 images tirées du partage C gelé de BOWS2 par classement SHA-256 déterministe des métadonnées déjà présentes dans le manifeste de 1ter, graine `FHAM-1quater-C-final-20261121`. Aucun pixel C n'a été consulté pour sélectionner cet échantillon.
- **F :** les 200 images du partage F BOSSBase réservées par le manifeste hash-only de 1ter; aucune nouvelle sélection.
- Les chemins, identifiants et SHA-256 des deux listes figurent dans `results/stability_step1/step1quater/run/final_freeze/C_final_manifest_hash_only.csv` et `F_final_manifest_hash_only.csv`. Leurs empreintes sont consignées dans `preopen_sizing_and_manifest_lock.json` et son fichier `.sha256` adjacent.
- La configuration appliquée reste celle du gel G-Q2 : `p=10 %, q=5 %, m=2, B=4`, `config_id=50`. Chaque corpus est mesuré une fois, avec JPEG 75 et bruit σ = 2. Les résultats JPEG 65 et bruit σ = 2,5 restent descriptifs et sans rôle dans G-Q4.

## Statut avant ouverture

Cette note et les deux manifestes sont gelés avant l'accès aux pixels C/F. Après le gel, les pixels de C et F peuvent être lus pour le passage unique prévu en section 8 du protocole principal. Toute impossibilité de retrouver un fichier dont le SHA-256 est attendu entraîne un arrêt pour ce corpus, sans remplacement ad hoc.
