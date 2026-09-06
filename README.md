# Le Monde en clair — V1

Tableau de bord Streamlit qui sélectionne et explique les principales actualités de 15 pays.

## Fonctions

- synthèse mondiale limitée à 15 sujets ;
- fiches nationales par cartes-drapeaux cliquables ;
- niveaux Majeur, Important et À suivre ;
- classement par impact, récence et qualité générale de la source ;
- filtres de période et de thème ;
- explication « Pourquoi c'est important » ;
- liens vers les sources ;
- export CSV ;
- cache de 30 minutes et fonctionnement sans clé API.

## Déploiement Streamlit

1. Copier tous les fichiers à la racine du dépôt GitHub.
2. Commit puis Push.
3. Dans Streamlit Community Cloud, sélectionner `app.py`.

## Actualisation

Les informations sont récupérées au chargement puis conservées 30 minutes en cache. Aucune clé API n'est nécessaire.

## Limites

Le moteur de classement est heuristique. Il sert à réduire le bruit, pas à certifier la véracité d'un article. La V1 travaille principalement avec des résultats francophones ; la comparaison systématique entre médias nationaux et internationaux est prévue pour une version ultérieure.

