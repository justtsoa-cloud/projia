// Nouveautés de chaque version, présentées au premier lancement après une mise à jour.
// Contenu embarqué (aucun réseau) ; français par défaut, anglais disponible.

import 'package:flutter/material.dart';

class NewsItem {
  const NewsItem(this.icon, this.fr, this.frText, this.en, this.enText, {this.mg, this.mgText});
  final IconData icon;
  final String fr, frText, en, enText;
  final String? mg, mgText; // malgache (sinon français, langue seconde à Madagascar)

  String title(String locale) => locale == 'en' ? en : (locale == 'mg' ? mg ?? fr : fr);
  String text(String locale) => locale == 'en' ? enText : (locale == 'mg' ? mgText ?? frText : frText);
}

const whatsNew = <String, List<NewsItem>>{
  '0.2.10': [
    NewsItem(Icons.brush_outlined, 'Les demandes d\'image ne partent plus vers le texte',
        '« Draw… », « dessine… » donnent toujours une vraie image, même après avoir modifié le message. Si un modèle de texte prétend avoir créé l\'image, Tontolo bascule tout seul vers la création.',
        'Image requests no longer go to text',
        '“Draw…” always produces a real image, even after editing the message. If a text model claims it created the image, Tontolo switches to real image creation.',
        mg: 'Tsy lasa any amin\'ny soratra intsony ny fangatahana sary',
        mgText: 'Sary tena izy hatrany no azo amin\'ny « Manaova sary… », na dia efa novaina aza ny hafatra. Raha milaza ho namorona sary ny modely soratra, mifindra ho azy amin\'ny famoronana sary i Tontolo.'),
    NewsItem(Icons.shield_outlined, 'Sécurité renforcée',
        'Audit complet : téléchargements vidéo bornés, protection contre les images piégées et les flux XML malveillants, réglages sensibles verrouillés.',
        'Stronger security',
        'Full audit: bounded video downloads, protection against booby-trapped images and malicious XML feeds, sensitive settings locked.',
        mg: 'Fiarovana nohamafisina',
        mgText: 'Fanaraha-maso feno: voafetra ny fisintonana horonan-tsary, voaaro amin\'ny sary misy fandrika sy ny XML ratsy, voahidy ny kirakira saro-pady.'),
    NewsItem(Icons.person_outline, 'Auteur et statistiques anonymes',
        'Tontolo est conçu par RANIRIAMANJAKA Antsa (github.com/raantss18). Des statistiques anonymes l\'aident à l\'améliorer — jamais vos messages — désactivables dans Réglages.',
        'Author and anonymous statistics',
        'Tontolo is made by RANIRIAMANJAKA Antsa (github.com/raantss18). Anonymous statistics help improve it — never your messages — and can be turned off in Settings.',
        mg: 'Mpamorona sy antontan\'isa tsy mitonona anarana',
        mgText: 'RANIRIAMANJAKA Antsa (github.com/raantss18) no namorona an\'i Tontolo. Antontan\'isa tsy mitonona anarana no manampy azy hanatsara — tsy alefa mihitsy ny hafatrao — azo atsahatra ao amin\'ny Kirakira.'),
  ],
  '0.2.9': [
    NewsItem(Icons.notifications_active_outlined, 'Prévenu quand c\'est de nouveau disponible',
        'Si un modèle ou la création d\'images/vidéos est en pause, Tontolo affiche l\'heure de retour et vous envoie une notification quand c\'est reparti. Un bouton « Régénérer » relance d\'un geste.',
        'Notified when it is back',
        'If a model or image/video creation is paused, Tontolo shows when it will be back and sends you a notification when it is. A “Regenerate” button retries in one tap.',
        mg: 'Ampandrenesina rehefa misy indray',
        mgText: 'Raha mijanona ny modely iray na ny famoronana sary/horonan-tsary, asehon\'i Tontolo ny ora hiverenany ary andefasany fampandrenesana rehefa mandeha indray. Bokotra « Avereno » no mamerina azy.'),
    NewsItem(Icons.translate, 'Malagasy et anglais complets',
        'Toute l\'application est traduite en malagasy et en anglais, et Tontolo répond dans la langue choisie. Les demandes d\'images en malagasy (« Manaova sary… ») sont bien comprises.',
        'Full Malagasy and English',
        'The whole app is translated into Malagasy and English, and Tontolo answers in the chosen language. Image requests in Malagasy are understood.',
        mg: 'Malagasy sy anglisy feno',
        mgText: 'Voadika amin\'ny teny malagasy sy anglisy ny fampiharana manontolo, ary mamaly amin\'ny fiteny nofidinao i Tontolo. Azo tsara ny fangatahana sary amin\'ny teny malagasy (« Manaova sary… »).'),
    NewsItem(Icons.cloud_upload_outlined, 'Message envoyé au retour du réseau',
        'Sans connexion, votre message attend et part tout seul dès que le réseau revient.',
        'Sent when the network is back',
        'Without a connection, your message waits and is sent automatically when the network returns.',
        mg: 'Alefa rehefa miverina ny tambajotra',
        mgText: 'Raha tsy misy fifandraisana, miandry ny hafatrao ary lasa ho azy raha vao miverina ny tambajotra.'),
    NewsItem(Icons.monitor_heart_outlined, 'État des modèles et réponse rapide',
        'Nouvelle page « État des modèles » (prêts, en pause, épuisés, heure de retour) et option « Réponse rapide d\'abord » dans Personnalisation.',
        'Model status and fast answers',
        'New “Model status” page (ready, paused, exhausted, return time) and a “Fast answers first” option in Personalisation.',
        mg: 'Toetran\'ny modely sy valiny haingana',
        mgText: 'Pejy vaovao « Toetran\'ireo modely » (vonona, mijanona, lany, ora hiverenany) sy safidy « Valiny haingana aloha » ao amin\'ny Fanamboarana manokana.'),
  ],
  '0.2.8': [
    NewsItem(Icons.dashboard_customize_outlined, 'Accueil en raccourcis',
        'Huit raccourcis colorés pour démarrer d\'un geste : image, vidéo, retouche, recherche, traduction, explication, résumé, animation de photo. Plus trois idées qui changent chaque jour.',
        'Shortcut home screen',
        'Eight colourful shortcuts to start in one tap: image, video, retouch, search, translate, explain, summarize, animate a photo. Plus three ideas that change daily.'),
    NewsItem(Icons.circle, 'Pastille de santé',
        'Le bouton « Auto » porte une pastille : verte (plusieurs modèles gratuits prêts), orange (peu de choix), rouge (aucun, avec l\'heure de retour). Appui long : fixer un des meilleurs modèles d\'un geste.',
        'Health dot',
        'The “Auto” button now has a dot: green (several free models ready), orange (few), red (none, with the return time). Long-press: pin one of the best models in one tap.'),
  ],
  '0.2.7': [
    NewsItem(Icons.movie_outlined, 'Vidéos gratuites',
        'Demandez « crée une vidéo d\'un renard dans la neige », ou joignez une photo et dites « anime cette photo ». Vidéos de quelques secondes, sans clé (quelques-unes par jour ; une clé Hugging Face gratuite en donne plus).',
        'Free videos',
        'Ask “make a video of a fox in the snow”, or attach a photo and say “animate this photo”. Short clips, no key needed (a few per day; a free Hugging Face key gives more).'),
    NewsItem(Icons.system_update, 'Mises à jour plus fiables',
        'La recherche de mise à jour fonctionne même quand GitHub limite les requêtes (réseau mobile), dit clairement le résultat, et présente tous les changements des versions sautées.',
        'More reliable updates',
        'Update checks now work even when GitHub rate-limits requests (mobile networks), always report the result, and show every change from skipped versions.'),
  ],
  '0.2.6': [
    NewsItem(Icons.menu, 'Plus de place pour discuter',
        'Créations et Réglages sont maintenant dans le volet des discussions (☰). La barre du bas disparaît sur téléphone ; le bouton retour ramène à la discussion.',
        'More room to chat',
        'Creations and Settings now live in the conversations drawer (☰). The bottom bar is gone on phones; Back returns to the chat.'),
  ],
  '0.2.5': [
    NewsItem(Icons.wifi_off, 'Coupure réseau : fini la cascade de bascules',
        'Quand c\'est votre connexion qui tombe, Tontolo le détecte, attend le retour du réseau et reprend avec le même modèle au lieu d\'essayer tous les modèles un par un.',
        'Network drop: no more switch cascade',
        'When your own connection drops, Tontolo detects it, waits for the network and resumes with the same model instead of trying every model one by one.'),
    NewsItem(Icons.short_text, 'Bascules résumées',
        'Une série de bascules tient sur une seule ligne, avec le nombre total.',
        'Compact switches',
        'A run of model switches now fits on one line, with the total count.'),
  ],
  '0.2.4': [
    NewsItem(Icons.functions, 'Formules plus robustes',
        'Les formules dans les tableaux s\'affichent correctement, et un « \$ » oublié par le modèle ne mélange plus deux formules.',
        'More robust formulas',
        'Formulas inside tables now render correctly, and a stray “\$” from the model no longer merges two formulas.'),
    NewsItem(Icons.timer_outlined, 'Images : moins d\'attente',
        'Si le service gratuit d\'images est indisponible, Tontolo renonce au bout d\'environ 90 secondes au lieu de 6 minutes.',
        'Images: less waiting',
        'If the free image service is down, Tontolo gives up after about 90 seconds instead of 6 minutes.'),
  ],
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

/// Nouveautés de toutes les versions comprises entre `since` (exclue) et `upTo` (incluse),
/// de la plus récente à la plus ancienne : utile quand on saute plusieurs mises à jour.
List<(String, List<NewsItem>)> newsBetween(String since, String upTo) {
  List<int> p(String s) => RegExp(r'\d+').allMatches(s).map((m) => int.parse(m[0]!)).toList();
  int cmp(String a, String b) {
    final x = p(a), y = p(b);
    for (var i = 0; i < 3; i++) {
      final d = (i < x.length ? x[i] : 0) - (i < y.length ? y[i] : 0);
      if (d != 0) return d;
    }
    return 0;
  }

  final versions = whatsNew.keys
      .where((v) => (since.isEmpty || cmp(v, since) > 0) && cmp(v, upTo) <= 0)
      .toList()
    ..sort((a, b) => cmp(b, a));
  return [for (final v in versions) (v, whatsNew[v]!)];
}
