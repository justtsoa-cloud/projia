// Nouveautés de chaque version, présentées au premier lancement après une mise à jour.
// Contenu embarqué (aucun réseau) ; français par défaut, anglais disponible.

import 'package:flutter/material.dart';

class NewsItem {
  const NewsItem(this.icon, this.fr, this.frText, this.en, this.enText);
  final IconData icon;
  final String fr, frText, en, enText;

  String title(String locale) => locale == 'en' ? en : fr;
  String text(String locale) => locale == 'en' ? enText : frText;
}

const whatsNew = <String, List<NewsItem>>{
  '0.2.3': [
    NewsItem(Icons.auto_fix_high, 'Retouche fidèle de vos photos',
        'Une consigne comme « édite cette photo, style professionnel, sans changer la personne » retouche vraiment la photo (lumière, contraste, couleurs, netteté, noir et blanc, vintage…) sur votre téléphone : la personne et la composition ne changent pas, et rien n\'est envoyé en ligne.',
        'Faithful photo retouching',
        'An instruction like “edit this photo, professional style, without changing the person” really retouches the photo (light, contrast, colour, sharpness, B&W, vintage…) on your phone: the person and composition stay the same and nothing is sent online.'),
    NewsItem(Icons.auto_awesome, 'Bascule automatique vers l\'image',
        'Si un modèle de texte répond « je ne peux pas générer d\'images », Tontolo passe tout seul à la création d\'image, sans que vous ayez à relancer.',
        'Automatic switch to images',
        'If a text model says “I can\'t generate images”, Tontolo switches to image creation by itself — no need to retry.'),
    NewsItem(Icons.spellcheck, 'Vos demandes mieux comprises',
        '« crée la photo », « fais-moi un paysage », « vas-y refais »… sont reconnus comme des demandes d\'image, y compris quand ils suivent une demande précédente.',
        'Better understanding',
        '“create the photo”, “make me a landscape”, “go ahead, redo it”… are now recognised as image requests, even as follow-ups.'),
  ],
  '0.2.2': [
    NewsItem(Icons.auto_fix_high, 'Retouche créative de vos photos',
        'Aucun service gratuit ne retouche vraiment une photo : Tontolo la fait décrire par une IA gratuite à vision, puis recrée une image avec votre transformation. Un message l\'indique clairement.',
        'Creative photo editing',
        'No free service truly retouches photos: Tontolo has a free vision AI describe it, then recreates an image with your transformation. A message says so clearly.'),
    NewsItem(Icons.photo_size_select_large, 'Photos allégées',
        'Les photos jointes sont réduites avant l\'envoi : plus rapide, et compatible avec les IA gratuites.',
        'Lighter photos', 'Attached photos are resized before sending: faster and compatible with free AIs.'),
  ],
  '0.2.1': [
    NewsItem(Icons.restart_alt, 'L\'application ne s\'arrête plus',
        'Quitter l\'application puis la rouvrir fonctionne : le moteur déjà démarré est retrouvé au lieu de planter.',
        'No more crash on reopen',
        'Leaving the app and reopening it now works: the already-running engine is reused instead of crashing.'),
    NewsItem(Icons.history_toggle_off, 'Vos réponses ne se perdent plus',
        'Quitter une discussion pendant que le modèle répond n\'interrompt plus rien : en y revenant, la réponse est là ou continue de s\'écrire.',
        'Your answers are never lost',
        'Leaving a chat while the model is answering no longer stops anything: when you come back, the answer is there or keeps streaming.'),
    NewsItem(Icons.swipe_vertical, 'Défilement libre',
        'Vous pouvez remonter le fil pendant que le modèle écrit ou réfléchit. Un bouton ramène en bas.',
        'Free scrolling',
        'Scroll back while the model writes or thinks. A button brings you back to the latest message.'),
    NewsItem(Icons.psychology_outlined, 'Réflexion visible',
        'Les modèles à raisonnement montrent leur réflexion en direct (repliable) au lieu d\'un écran vide.',
        'Visible reasoning',
        'Reasoning models now show their thinking live (collapsible) instead of an empty screen.'),
    NewsItem(Icons.image_outlined, 'Images plus fiables',
        'Nouvelles tentatives automatiques, et « Réessayer » relance bien l\'image au lieu de produire du texte.',
        'More reliable images',
        'Automatic retries, and “Retry” now reruns the image instead of producing text.'),
    NewsItem(Icons.system_update, 'Mises à jour mises en avant',
        'Un résumé des changements s\'affiche dès qu\'une version est prête, et cette page après l\'installation.',
        'Updates made visible',
        'A summary of changes appears as soon as a version is ready, and this page after installing.'),
  ],
  '0.2.0': [
    NewsItem(Icons.bookmark_added_outlined, 'Mémoire qui se compacte toute seule',
        'Dites « souviens-toi que… » : Tontolo retient vos préférences sur l\'appareil.',
        'Self-compacting memory', 'Say “remember that…”: Tontolo keeps your preferences on the device.'),
    NewsItem(Icons.lock_open, 'Plus de 30 modèles sans clé',
        'Kilo Code, LLM7 et OVHcloud s\'ajoutent à Pollinations : la bascule marche sans aucune clé.',
        'Over 30 models without a key',
        'Kilo Code, LLM7 and OVHcloud join Pollinations: fallback works with no key at all.'),
    NewsItem(Icons.volume_off_outlined, 'Lecture vocale arrêtable',
        'Un bouton lit et arrête la voix ; vitesse réglable.', 'Stoppable read-aloud',
        'One button starts and stops the voice; speed is adjustable.'),
  ],
};

List<NewsItem> newsFor(String version) => whatsNew[version] ?? const [];
