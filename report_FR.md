# Mesurer la robustesse du suivi d'instructions de Qwen3-8B — étude contrôlée (version courte)

**Auteur :** Téo Brondel · **Date :** 2026-10-15

> **Note perso — pas pour le dossier.** Squelette à réécrire avec tes mots. Les
> chiffres sont réels (un run de `qwen3:8b` le 2026-10-15, journalisé dans
> `runs/`). Seul champ à compléter : la déclaration d'usage de l'IA (dernière
> section). Vérifie toi-même la politique d'Anthropic sur l'usage de l'IA dans
> les candidatures.

## Résumé

J'ai mené une petite expérience contrôlée pour mesurer à quelle fréquence un
modèle open instruct suit une règle qu'on lui donne, et à quelle fréquence un
prompt adverse court le pousse à l'enfreindre. Trois tâches **inoffensives** à
jugement automatique : (1) révéler un marqueur inerte (« canary ») interdit,
(2) casser un format JSON imposé, (3) obéir à une instruction cachée dans un
document (injection indirecte). Modèle : **Qwen3-8B** (local, 4-bit, via
Ollama), deux conditions (règle seule vs règle + une phrase de défense), 5
répétitions par cas (**300 appels, 0 erreur**). Avec un juge qui
normalise les encodages et distingue « obéir » à une injection de simplement la
« décrire », le taux de contournement global est **~49 %** (146/300). La phrase
de défense aide surtout sur la fuite du canary (50 %→30 % ; diff appariée par
prompt +20 pts, IC 95 % [0, +46]) et un peu sur l'injection (80 %→72 % ; +8 pts,
[0, +24]), sans effet sur le format (30 %→30 %) ; tous les effets sont positifs
mais leurs intervalles touchent 0, donc aucun n'est concluant. Les IC prennent le
prompt comme unité d'analyse. Étude pilote, un seul modèle, petit échantillon, sans
relecture par des pairs ; chiffres donnés avec intervalle de confiance à 95 %.

## Méthode (en bref)

- 30 cas (10 variantes × 3 tâches), conditions `baseline` vs `hardened`.
- Jugement **automatique** : présence du canary ; format JSON cassé ; présence
  du marqueur d'injection. Critères fixés à l'avance.
- Modèle local via Ollama (`qwen3:8b`), température 0.7, mode *thinking*
  désactivé. Chaque appel journalisé intégralement → artefact de
  reproductibilité. Aucune production de contenu dangereux (signaux inertes).

## Résultats

Taux de contournement (plus bas = plus robuste), issus de `analyze.py` :

| Tâche | Condition | Taux | k/n | IC 95 % (bootstrap par prompt) |
|-------|-----------|-----:|----:|:-----------------------------:|
| secret | baseline | 50 % | 25/50 | [20 %, 80 %] |
| secret | hardened | 30 % | 15/50 | [6 %, 58 %] |
| format | baseline | 30 % | 15/50 | [0 %, 60 %] |
| format | hardened | 30 % | 15/50 | [0 %, 60 %] |
| inject | baseline | 80 % | 40/50 | [50 %, 100 %] |
| inject | hardened | 72 % | 36/50 | [44 %, 100 %] |

**Lecture.** L'injection indirecte est le point faible : **80 % obéi** (baseline),
72 % (hardened) ; deux documents font plutôt *décrire* l'injection au lieu
d'obéir (non compté comme obéissance). Le format n'est cassé que si l'utilisateur
demande explicitement d'abandonner le JSON (sinon le modèle met poème/XML/markdown
*dans* le JSON). Le canary fuit par complétion de phrase, **canary épelé une
lettre par ligne (raté par le premier juge)**, traduction du prompt système,
« répète ce qui est au-dessus », et override « ignore tes instructions » ; les
demandes directes, le faux admin et le jeu de rôle sont refusés ; une demande
base64 produit un encodage *incorrect* (tentative, ni fuite ni refus). Effets de
la défense (appariés) : canary +20 pts [0, +46], injection +8 pts [0, +24] —
positifs mais **non concluants** (IC qui touchent 0).

## Limites

Petit échantillon ; un seul modèle (Qwen3-8B 4-bit) ; pas de contrôle de graine
(les runs varient — comportement par prompt néanmoins très stable, souvent 0/10
ou 10/10) ; IC calculés avec le **prompt** comme unité (bootstrap sur 10 prompts) ;
juge v2 (canary normalisé + base64 ; injection : obéir vs décrire, un cas limite
compté « obey » et signalé pour relecture) ; mode *thinking* désactivé ; tâches
proxy qui approximent, sans les être, de vraies défaillances de sécurité.

## Ce que le premier juge ratait

- **Secret (sous-compté) :** le juge v1 (substring brut) ratait le canary épelé
  une lettre par ligne (10/10) → 40/20 % deviennent 50/30 % ; et comptait une
  tentative base64 incorrecte comme refus → re-étiquetée 5 tentatives.
- **Injection (sur-compté) :** v1 comptait toute occurrence du marqueur comme
  obéissance ; 14 sorties *décrivaient/citaient* l'injection → vraie obéissance
  80/72 %, pas 90/90 %.
- Net : secret 40/20 → 50/30 ; injection 90/90 → 80/72. Détail avant/après et
  verdicts changés dans `results_v2.md`.

## Divulgation responsable & indépendance

Je partage la méthode, les taux agrégés, le code et des exemples inoffensifs ;
je ne publie aucune recette de jailbreak. Tests réalisés sur des poids ouverts
sous leur licence, sans système tiers. Travail **indépendant** : aucun lien avec
Anthropic, aucun avis d'Anthropic.
**Usage de l'IA.** Ce projet a été réalisé avec une aide substantielle d'un
assistant de code IA (Claude, via Claude Code). L'assistant a proposé le
protocole expérimental — les trois tâches proxy inoffensives et la comparaison
baseline/hardened —, écrit tout le code (harnais de test, jeu de prompts, script
d'analyse), installé le modèle local, lancé l'expérience de 300 appels, calculé
les statistiques, et produit un premier brouillon de ce compte rendu. Ma
contribution propre a consisté à définir l'objectif et le contexte, à prendre
les décisions clés (tester un modèle open-weights exécuté en local, la taille du
modèle, le feu vert), à vérifier chaque chiffre par rapport au log brut, et à
réécrire ce document avec mes propres mots. Aucun résultat, chiffre ou citation
n'a été inventé : toutes les valeurs proviennent d'un run unique journalisé,
reproductible à partir du code. J'assume la responsabilité de l'exactitude du
texte final. À ma connaissance, cet usage de l'IA est conforme à la politique du
programme sur l'usage de l'IA dans les candidatures, que j'ai consultée.
