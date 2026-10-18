// Rappel subtil : consentement, plafonds, heures calmes, actualité récente et pertinente.
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:tontolo/core/comeback.dart';
import 'package:tontolo/l10n/strings.dart';

const rss = '''<?xml version="1.0"?><rss><channel><title>Flux</title>
<item><title><![CDATA[Un volcan en éruption aux Philippines]]></title><link>https://exemple.org/a</link>
<pubDate>Sat, 17 Oct 2026 08:30:00 GMT</pubDate></item>
<item><title>Nouvelle technique pour mesurer la photosynthèse &amp; le climat</title><link>https://exemple.org/b</link>
<pubDate>Sun, 18 Oct 2026 06:00:00 +0200</pubDate></item>
<item><title>Trop vieux pour être chaud</title><link>https://exemple.org/c</link>
<pubDate>Mon, 05 Oct 2026 08:30:00 GMT</pubDate></item>
<item><title>Lien non sûr à écarter</title><link>http://exemple.org/d</link></item>
</channel></rss>''';

const atom = '''<feed><entry><title>Les fractions au collège : ce qui change</title>
<link href="https://exemple.org/e" rel="alternate"/><updated>2026-10-18T07:00:00Z</updated></entry></feed>''';

void main() {
  final now = DateTime.utc(2026, 10, 18, 12);

  test('flux RSS et Atom lus ; liens non https écartés', () {
    final items = Comeback.parseFeed(rss);
    expect(items.map((h) => h.title), contains('Nouvelle technique pour mesurer la photosynthèse & le climat'));
    expect(items.any((h) => h.link.startsWith('http://')), isFalse);
    expect(items.first.at, DateTime.utc(2026, 10, 17, 8, 30));
    expect(items[1].at, DateTime.utc(2026, 10, 18, 4)); // +0200 converti
    final a = Comeback.parseFeed(atom);
    expect(a.single.link, 'https://exemple.org/e');
    expect(a.single.at, DateTime.utc(2026, 10, 18, 7));
  });

  test('titre récent et pertinent, jamais plus vieux que 4 jours', () {
    final items = Comeback.parseFeed(rss);
    expect(Comeback.pick(items, ['la photosynthèse'], now)!.title, contains('photosynthèse'));
    expect(Comeback.pick(items, ['les volcans'], now)!.title, contains('volcan'));
    expect(Comeback.pick(items, ['autre chose'], now)!.title, contains('volcan')); // plus récent du flux
    final old = Comeback.parseFeed(rss).where((h) => h.title.startsWith('Trop vieux')).toList();
    expect(Comeback.pick(old, ['x'], now), isNull); // rien de chaud : pas de rappel
  });

  test('domaine selon les thèmes', () {
    expect(Comeback.domainOf(['la photosynthèse']), Domain.science);
    expect(Comeback.domainOf(['Apprendre Python']), Domain.tech);
    expect(Comeback.domainOf(['Révision examen']), Domain.education);
    expect(Comeback.domainOf(['La Guerre froide']), Domain.history);
    expect(Comeback.domainOf(['Une recette']), Domain.general);
  });

  test('désactivé tant que non accepté', () {
    expect(Comeback.fireTime(pausedAt: now, enabled: false), isNull);
  });

  test('rien avant 3 jours ; 10 h 30 locale (jamais la nuit)', () {
    final paused = DateTime(2026, 10, 18, 23, 40);
    final t = Comeback.fireTime(pausedAt: paused, enabled: true)!;
    expect(t, DateTime(2026, 10, 21, 10, 30));
    expect(t.difference(paused).inDays, greaterThanOrEqualTo(2));
  });

  test('jamais deux rappels à moins de 4 jours', () {
    final paused = DateTime(2026, 10, 18, 9);
    final last = DateTime(2026, 10, 20, 10, 30); // un rappel vient de partir
    final t = Comeback.fireTime(pausedAt: paused, lastFired: last, enabled: true)!;
    expect(t, DateTime(2026, 10, 24, 10, 30)); // 4 jours après le dernier
  });

  test('récupération : réponse en erreur ou flux sans titre chaud = aucun rappel', () async {
    final bad = MockClient((_) async => http.Response('', 503));
    expect(await Comeback.fetch(['volcans'], 'fr', now, client: bad), isNull);
    final ok = MockClient((r) async {
      expect(r.headers.keys, isNot(contains('Cookie'))); // aucun identifiant
      return http.Response(rss, 200, headers: {'content-type': 'application/xml'});
    });
    expect((await Comeback.fetch(['volcans'], 'fr', now, client: ok))!.link, 'https://exemple.org/a');
  });

  test('textes dans les trois langues', () {
    for (final k in ['cb_ask', 'cb_ask_help', 'cb_yes', 'cb_no', 'cb_setting', 'news_label', 'news_talk', 'news_open', 'news_prompt']) {
      for (final l in ['fr', 'en', 'mg']) {
        expect(tr(l, k), isNot(k), reason: '$l/$k');
      }
    }
  });
}
