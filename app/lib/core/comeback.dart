// Rappel subtil (P3) : après quelques jours sans ouvrir Tontolo, UNE notification locale avec un
// titre d'actualité de votre domaine, tiré d'un flux public gratuit lu sur l'appareil. Rien
// n'est envoyé à un serveur de Tontolo ; le profil d'intérêts ne quitte jamais l'appareil.
//
// Garde-fous (testés) : désactivé tant que la personne n'a pas accepté ; rien les 3 premiers
// jours ; jamais deux rappels à moins de 4 jours ; jamais la nuit (10 h 30 locale) ; pas de
// notification s'il n'y a pas de titre récent et pertinent ; une seule par absence.
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'prefs.dart';

enum Domain { science, tech, education, history, general }

class Headline {
  const Headline(this.title, this.link, this.at);
  final String title;
  final String link;
  final DateTime? at;
}

class Comeback {
  Comeback._();

  static const absenceDays = 3;
  static const minGapDays = 4;
  static const maxAgeDays = 4;

  /// Domaine d'un ensemble de thèmes (titres de discussion nettoyés).
  static Domain domainOf(List<String> topics) {
    final blob = topics.join(' ').toLowerCase();
    bool has(List<String> words) => words.any(blob.contains);
    if (has(['code', 'python', 'program', 'informatique', 'ia ', 'intelligence artificielle', 'ordinateur',
      'logiciel', 'internet', 'robot', 'technolog', 'javascript', 'computer', 'software', ' ai '])) {
      return Domain.tech;
    }
    if (has(['photosynth', 'volcan', 'physique', 'chimie', 'biolog', 'svt', 'espace', 'planète', 'planete',
      'atome', 'cellule', 'climat', 'animal', 'plante', 'science', 'astronom', 'maths', 'mathém', 'fraction',
      'géométrie', 'physics', 'chemistry', 'space', 'energy', 'énergie'])) {
      return Domain.science;
    }
    if (has(['révision', 'revision', 'examen', 'bac', 'école', 'ecole', 'leçon', 'lecon', 'devoir', 'étudi',
      'etudi', 'university', 'school', 'lesson', 'exam', 'orthographe', 'grammaire', 'conjugaison'])) {
      return Domain.education;
    }
    if (has(['histoire', 'guerre', 'révolution', 'revolution', 'roi', 'empire', 'history', 'war', 'ancien'])) {
      return Domain.history;
    }
    return Domain.general;
  }

  /// Flux public gratuit, dans la langue de l'application quand il en existe un.
  static String feedFor(Domain d, String lang) {
    final fr = lang != 'en';
    switch (d) {
      case Domain.science:
        return fr ? 'https://www.futura-sciences.com/rss/actualites.xml' : 'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml';
      case Domain.tech:
        return fr ? 'https://www.franceinfo.fr/sciences.rss' : 'https://feeds.bbci.co.uk/news/technology/rss.xml';
      case Domain.education:
        return fr ? 'https://theconversation.com/fr/articles.atom' : 'https://feeds.bbci.co.uk/news/education/rss.xml';
      case Domain.history:
        return fr ? 'https://theconversation.com/fr/articles.atom' : 'https://feeds.bbci.co.uk/news/world/rss.xml';
      case Domain.general:
        return fr ? 'https://www.rfi.fr/fr/rss' : 'https://feeds.bbci.co.uk/news/world/rss.xml';
    }
  }

  static String _clean(String s) => s
      .replaceAll(RegExp(r'<!\[CDATA\[|\]\]>'), '')
      .replaceAll(RegExp(r'<[^>]+>'), '')
      .replaceAll('&amp;', '&')
      .replaceAll('&quot;', '"')
      .replaceAll('&#39;', "'")
      .replaceAll('&apos;', "'")
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAllMapped(RegExp(r'&#x([0-9A-Fa-f]+);'), (m) => String.fromCharCode(int.parse(m[1]!, radix: 16)))
      .replaceAllMapped(RegExp(r'&#(\d+);'), (m) => String.fromCharCode(int.parse(m[1]!)))
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();

  static DateTime? _date(String? raw) {
    if (raw == null) return null;
    final iso = DateTime.tryParse(raw.trim());
    if (iso != null) return iso;
    // RFC 822 : « Sat, 18 Oct 2026 08:30:00 GMT » ou « +0200 ».
    final m = RegExp(r'(\d{1,2}) (\w{3}) (\d{4}) (\d{2}):(\d{2})(?::(\d{2}))?\s*([+-]\d{4}|GMT|UT)?').firstMatch(raw);
    if (m == null) return null;
    const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
    final mo = months.indexOf(m[2]!.toLowerCase());
    if (mo < 0) return null;
    var d = DateTime.utc(int.parse(m[3]!), mo + 1, int.parse(m[1]!), int.parse(m[4]!), int.parse(m[5]!), int.parse(m[6] ?? '0'));
    final z = m[7];
    if (z != null && z.length == 5) {
      final off = Duration(hours: int.parse(z.substring(1, 3)), minutes: int.parse(z.substring(3)));
      d = z.startsWith('+') ? d.subtract(off) : d.add(off);
    }
    return d;
  }

  /// Articles d'un flux RSS ou Atom (lecture tolérante, bornée : 60 articles).
  static List<Headline> parseFeed(String xml) {
    final out = <Headline>[];
    final items = RegExp(r'<(item|entry)\b[^>]*>(.*?)</\1>', dotAll: true).allMatches(xml);
    for (final m in items.take(60)) {
      final body = m[2]!;
      String? tag(String name) => RegExp('<$name\\b[^>]*>(.*?)</$name>', dotAll: true).firstMatch(body)?[1];
      final title = _clean(tag('title') ?? '');
      var link = _clean(tag('link') ?? '');
      if (link.isEmpty) link = RegExp(r'<link[^>]*href="([^"]+)"').firstMatch(body)?[1] ?? '';
      final when = _date(tag('pubDate') ?? tag('published') ?? tag('updated') ?? tag('dc:date'));
      if (title.length >= 12 && link.startsWith('https://')) out.add(Headline(title, link, when));
    }
    return out;
  }

  /// Titre récent et pertinent : d'abord ceux qui partagent un mot avec les thèmes de la personne,
  /// sinon le plus récent du domaine ; rien de plus vieux que 4 jours (« bien chaud »).
  static Headline? pick(List<Headline> items, List<String> topics, DateTime now) {
    final fresh = [
      for (final h in items)
        if (h.at == null || now.difference(h.at!).inDays <= maxAgeDays) h
    ];
    if (fresh.isEmpty) return null;
    final words = {
      for (final t in topics)
        for (final w in t.toLowerCase().split(RegExp(r'[^a-zà-ÿ0-9]+')))
          if (w.length >= 5) w
    };
    for (final h in fresh) {
      final lower = h.title.toLowerCase();
      if (words.any(lower.contains)) return h;
    }
    return fresh.first;
  }

  /// Heure du rappel (10 h 30 locale, jamais la nuit) : 3 jours après la fermeture, et au moins
  /// 4 jours après le rappel précédent. `null` si la personne n'a pas accepté.
  static DateTime? fireTime({required DateTime pausedAt, DateTime? lastFired, required bool enabled}) {
    if (!enabled) return null;
    var base = pausedAt.add(const Duration(days: absenceDays));
    if (lastFired != null && base.difference(lastFired).inDays < minGapDays) {
      base = lastFired.add(const Duration(days: minGapDays));
    }
    return DateTime(base.year, base.month, base.day, 10, 30);
  }

  /// Récupère le titre du jour (sur l'appareil, sans identifiant) ; `null` s'il n'y en a pas.
  static Future<Headline?> fetch(List<String> topics, String lang, DateTime now, {http.Client? client}) async {
    final transport = client ?? http.Client();
    try {
      final r = await transport
          .get(Uri.parse(feedFor(domainOf(topics), lang)), headers: {'User-Agent': 'Tontolo'})
          .timeout(const Duration(seconds: 12));
      if (r.statusCode != 200) return null;
      return pick(parseFeed(utf8.decode(r.bodyBytes, allowMalformed: true)), topics, now);
    } catch (_) {
      return null;
    } finally {
      if (client == null) transport.close();
    }
  }

  // --- État conservé sur l'appareil ---------------------------------------------------------
  static Map<String, dynamic>? stored(Prefs prefs) {
    try {
      final v = jsonDecode(prefs.cbNews);
      return v is Map<String, dynamic> && v['title'] != null ? v : null;
    } catch (_) {
      return null;
    }
  }
}
