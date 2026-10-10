// « À propos » : version, licence et attributions obligatoires
// (Artificial Analysis, LMArena CC BY 4.0, OpenRouter, Pollinations…).

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/updater.dart';
import '../main.dart';

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  static const attributions = [
    ('Artificial Analysis', 'https://artificialanalysis.ai/', 'Indices d\'intelligence, de code, de maths et de vitesse.'),
    ('LMArena', 'https://lmarena.ai/', 'Classements par catégorie — jeu de données sous licence CC BY 4.0.'),
    ('OpenRouter', 'https://openrouter.ai/', 'Catalogue des modèles, prix et capacités.'),
    ('awesome-free-llm-apis', 'https://github.com/mnfst/awesome-free-llm-apis', 'Fournisseurs gratuits (CC0 1.0).'),
    ('Pollinations', 'https://pollinations.ai/', 'Texte et images sans clé.'),
  ];

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(context.t('about'))),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          Center(child: Image.asset('assets/icon.png', width: 80, height: 80)),
          const SizedBox(height: 8),
          Center(child: Text('Tontolo $appVersion', style: Theme.of(context).textTheme.titleLarge)),
          const SizedBox(height: 4),
          const Center(child: Text('Hub d\'IA libre et gratuit — licence Apache-2.0')),
          TextButton(
            onPressed: () => launchUrl(Uri.parse('https://github.com/$repo')),
            child: const Text('github.com/raantss18/tontolo'),
          ),
          const Divider(),
          Text(context.t('attributions'), style: Theme.of(context).textTheme.titleMedium),
          for (final (name, url, use) in attributions)
            ListTile(
              title: Text(name),
              subtitle: Text(use),
              trailing: const Icon(Icons.open_in_new, size: 18),
              onTap: () => launchUrl(Uri.parse(url)),
            ),
          const Divider(),
          ListTile(
            title: Text(context.t('license')),
            subtitle: const Text('Licences des composants open source'),
            onTap: () => showLicensePage(context: context, applicationName: 'Tontolo', applicationVersion: appVersion),
          ),
        ]),
      );
}
