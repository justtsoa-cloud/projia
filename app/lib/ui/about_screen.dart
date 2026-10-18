// « À propos » : version, licence et attributions obligatoires
// (Artificial Analysis, LMArena CC BY 4.0, OpenRouter, Pollinations…).

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/updater.dart';
import '../core/author.dart';
import '../main.dart';
import 'feedback_card.dart';

/// Page de la dernière version (APK, AppImage) : même adresse que le QR code embarqué.
const downloadUrl = 'https://github.com/raantss18/tontolo/releases/latest';

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  static const attributions = [
    ('Artificial Analysis', 'https://artificialanalysis.ai/', 'attr_aa'),
    ('LMArena', 'https://lmarena.ai/', 'attr_lma'),
    ('OpenRouter', 'https://openrouter.ai/', 'attr_or'),
    ('awesome-free-llm-apis', 'https://github.com/mnfst/awesome-free-llm-apis', 'attr_free'),
    ('Pollinations', 'https://pollinations.ai/', 'attr_poll'),
    ('Hugging Face — LTX-Video', 'https://huggingface.co/spaces/Lightricks/ltx-video-distilled', 'attr_ltx'),
  ];

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(context.t('about'))),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          Center(child: Image.asset('assets/icon.png', width: 80, height: 80)),
          const SizedBox(height: 8),
          Center(child: Text('Tontolo $appVersion', style: Theme.of(context).textTheme.titleLarge)),
          const SizedBox(height: 4),
          Center(child: Text(context.t('about_tagline'), textAlign: TextAlign.center)),
          TextButton(
            onPressed: () => launchUrl(Uri.parse('https://github.com/$repo')),
            child: const Text('github.com/raantss18/tontolo'),
          ),
          const Divider(),
          // QR code vers la dernière version : pour installer Tontolo sur un autre téléphone.
          Center(
            child: InkWell(
              borderRadius: BorderRadius.circular(16),
              onTap: () => launchUrl(Uri.parse(downloadUrl), mode: LaunchMode.externalApplication),
              child: Padding(
                padding: const EdgeInsets.all(8),
                child: Column(children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(12)),
                    child: Image.asset('assets/qr/download.png', width: 168, height: 168,
                        filterQuality: FilterQuality.none, semanticLabel: context.t('qr_download')),
                  ),
                  const SizedBox(height: 8),
                  Text(context.t('qr_download'), style: Theme.of(context).textTheme.titleSmall),
                  Text(context.t('qr_download_help'), textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall),
                ]),
              ),
            ),
          ),
          const Divider(),
          AppRatingTile(prefs: AppScope.of(context).prefs),
          const Divider(),
          Text(context.t('author'), style: Theme.of(context).textTheme.titleMedium),
          const AuthorCard(),
          const Divider(),
          Text(context.t('attributions'), style: Theme.of(context).textTheme.titleMedium),
          for (final (name, url, use) in attributions)
            ListTile(
              title: Text(name),
              subtitle: Text(context.t(use)),
              trailing: const Icon(Icons.open_in_new, size: 18),
              onTap: () => launchUrl(Uri.parse(url)),
            ),
          const Divider(),
          ListTile(
            title: Text(context.t('license')),
            subtitle: Text(context.t('oss_licenses')),
            onTap: () => showLicensePage(context: context, applicationName: 'Tontolo', applicationVersion: appVersion),
          ),
        ]),
      );
}


/// Carte de l'auteur : nom et contacts cliquables (GitHub, e-mail, téléphone, WhatsApp).
class AuthorCard extends StatelessWidget {
  const AuthorCard({super.key, this.dense = false});
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final rows = [
      (Icons.code, authorGithub, authorGithubUrl),
      (Icons.mail_outline, authorEmail, authorEmailUrl),
      (Icons.phone_outlined, authorPhone, authorPhoneUrl),
      (Icons.chat_outlined, 'WhatsApp $authorPhone', authorWhatsappUrl),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ListTile(
        dense: dense,
        contentPadding: EdgeInsets.zero,
        leading: const CircleAvatar(child: Icon(Icons.person_outline)),
        title: const Text(authorName, style: TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(context.t('author_role')),
      ),
      for (final (icon, label, url) in rows)
        ListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          leading: Icon(icon, size: 20),
          title: Text(label),
          onTap: () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
        ),
    ]);
  }
}
