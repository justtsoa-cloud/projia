// Nom et description d'un fournisseur dans la langue de l'app (traductions fournies par le
// cœur dans `i18n` ; le français est la valeur de base).
String providerText(Map<String, dynamic> p, String locale, String field) {
  final i18n = p['i18n'];
  if (locale != 'fr' && i18n is Map) {
    final t = i18n[locale];
    if (t is Map && t[field] != null) return '${t[field]}';
  }
  return '${p[field] ?? ''}';
}
