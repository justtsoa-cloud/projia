# Maquettes de l'écran principal

Deux propositions ont été étudiées (section 10 de la spécification). Choix retenu : **A**.

## Proposition A — « Conversation d'abord » (retenue)

```
Mobile (barre du bas)                     Desktop / tablette (barre latérale)
┌──────────────────────────┐              ┌────┬──────────────────────────────────┐
│ ☰  Projia               │              │ 💬 │ Projia                ⌕ Ctrl+K │
│──────────────────────────│              │ 🖼 │──────────────────────────────────│
│                          │              │ ⚙  │  Utilisateur : Résous x²−4=0     │
│   Bonjour 👋             │              │    │                                  │
│   [Résume un article]    │              │    │  Assistant · Gemma 4 31B ⓘ       │
│   [Dessine un phare]     │              │    │  $$x = \pm 2$$                   │
│   [Explique une formule] │              │    │                                  │
│                          │              │    │ ┌ Bascule → Qwen 3.8 (quota) ┐   │
│                          │              │    │                                  │
│──────────────────────────│              │    │──────────────────────────────────│
│ [Auto ▾]                 │              │    │ [Auto ▾]                         │
│ ＋ │ Écrire…          │ ➤ │              │    │ ＋ │ Écrire…  (Ctrl+Entrée)  │ ➤ │
│──────────────────────────│              └────┴──────────────────────────────────┘
│  💬 Chat   🖼 Créations  ⚙ │
└──────────────────────────┘
```

- Un seul écran principal ; l'historique est dans un tiroir (☰).
- Puce discrète « Auto ▾ » au-dessus du champ : sélecteur de modèle (F8).
- Bascules et retours : bandeau fin non bloquant dans le fil.
- 3 destinations : Chat, Créations, Réglages (≤ 3 appuis pour toute action courante).

## Proposition B — « Tableau de bord »

```
┌──────────────────────────┐
│ Projia     [Texte|Image|Son|Vidéo] │
│ Modèle : [Gemma 4 ▾]  Quotas ▮▮▮▯    │
│──────────────────────────│
│ conversation…            │
│──────────────────────────│
│ ＋ │ Écrire…          │ ➤ │
└──────────────────────────┘
```

- Onglets de modalité visibles, jauge de quotas et modèle affiché en permanence.

## Décision

**A** est retenue : B impose de choisir un « mode » (contraire au principe « pas de mode à
choisir », la modalité étant détectée) et charge l'écran principal (quotas, onglets).
A respecte l'épure, la divulgation progressive et l'adaptation mobile/desktop.
