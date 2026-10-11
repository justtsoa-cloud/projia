// Aide pas à pas pour obtenir la clé d'API de chaque fournisseur. Les noms de menus et de
// boutons restent ceux des sites (en anglais) pour que l'utilisateur les reconnaisse ;
// les phrases autour sont traduites (clés kg_* dans strings.dart).

class KeyGuide {
  const KeyGuide({
    required this.url,
    this.login = 'Google, GitHub',
    this.path = 'API Keys',
    this.button = 'Create API Key',
    this.prefix = '',
    this.cost = 'free',
    this.note,
  });

  final String url;
  final String login; // moyens de connexion proposés par le site
  final String path; // menu où se trouvent les clés
  final String button; // bouton qui crée la clé
  final String prefix; // début de la clé, pour vérifier qu'on a copié la bonne chose
  final String cost; // free | credits | trial | optional
  final String? note; // clé de traduction d'une remarque propre au fournisseur
}

const keyGuides = <String, KeyGuide>{
  'gemini': KeyGuide(url: 'https://aistudio.google.com/app/apikey', login: 'Google', path: 'Get API key', button: 'Create API key', prefix: 'AIza', note: 'kg_n_gemini'),
  'groq': KeyGuide(url: 'https://console.groq.com/keys', login: 'Google, GitHub, e-mail', prefix: 'gsk_', note: 'kg_n_groq'),
  'openrouter': KeyGuide(url: 'https://openrouter.ai/settings/keys', login: 'Google, GitHub, e-mail', button: 'Create Key', prefix: 'sk-or-', note: 'kg_n_openrouter'),
  'mistral': KeyGuide(url: 'https://console.mistral.ai/api-keys', login: 'Google, e-mail', button: 'Create new key', note: 'kg_n_mistral'),
  'huggingface': KeyGuide(url: 'https://huggingface.co/settings/tokens', login: 'e-mail, Google, GitHub', path: 'Settings › Access Tokens', button: 'Create new token', prefix: 'hf_', note: 'kg_n_huggingface'),
  'cohere': KeyGuide(url: 'https://dashboard.cohere.com/api-keys', login: 'Google, GitHub, e-mail', button: 'New Trial Key', cost: 'trial', note: 'kg_n_cohere'),
  'nvidia': KeyGuide(url: 'https://build.nvidia.com/settings/api-keys', login: 'e-mail, Google', button: 'Generate API Key', prefix: 'nvapi-', cost: 'trial', note: 'kg_n_nvidia'),
  'cloudflare': KeyGuide(url: 'https://dash.cloudflare.com/profile/api-tokens', login: 'e-mail', path: 'My Profile › API Tokens', button: 'Create Token › Workers AI', note: 'kg_n_cloudflare'),
  'kilo': KeyGuide(url: 'https://app.kilo.ai/profile', login: 'Google, GitHub', path: 'Profile', button: 'API Key'),
  'llm7': KeyGuide(url: 'https://token.llm7.io', login: 'Google, GitHub', path: 'Dashboard', button: 'Copy token', cost: 'optional'),
  'ollama': KeyGuide(url: 'https://ollama.com/settings/keys', login: 'Google, GitHub, e-mail', path: 'Settings › Keys', button: 'Add API key'),
  'ovh': KeyGuide(url: 'https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/', login: 'e-mail', path: 'Public Cloud › AI Endpoints › API keys', button: 'Create a new API key', cost: 'optional'),
  'aion': KeyGuide(url: 'https://www.aionlabs.ai/app/api-keys/', login: 'Google, e-mail', button: 'Create API key'),
  'zai': KeyGuide(url: 'https://open.bigmodel.cn/usercenter/apikeys', login: 'e-mail, téléphone', button: 'Add API key', note: 'kg_n_china'),
  'modelscope': KeyGuide(url: 'https://modelscope.cn/my/myaccesstoken', login: 'e-mail, téléphone', path: 'Access Token', button: 'Create', note: 'kg_n_china'),
  'siliconflow': KeyGuide(url: 'https://cloud.siliconflow.cn/account/ak', login: 'téléphone', button: 'Create API Key', prefix: 'sk-', note: 'kg_n_china'),
  'artificial-analysis': KeyGuide(url: 'https://artificialanalysis.ai/insights', login: 'Google, e-mail', path: 'Insights › API', button: 'Create API key', note: 'kg_n_aa'),
  // Serveurs payants (facturés à l'usage par le fournisseur ; plafond fixé dans Tontolo).
  'openai': KeyGuide(url: 'https://platform.openai.com/api-keys', login: 'Google, Microsoft, Apple, e-mail', button: 'Create new secret key', prefix: 'sk-', cost: 'credits', note: 'kg_n_openai'),
  'anthropic': KeyGuide(url: 'https://console.anthropic.com/settings/keys', login: 'Google, e-mail', button: 'Create Key', prefix: 'sk-ant-', cost: 'credits', note: 'kg_n_anthropic'),
  'deepseek': KeyGuide(url: 'https://platform.deepseek.com/api_keys', login: 'Google, e-mail', button: 'Create new API key', prefix: 'sk-', cost: 'credits', note: 'kg_n_deepseek'),
  'xai': KeyGuide(url: 'https://console.x.ai', login: 'X, Google, e-mail', path: 'API Keys', button: 'Create API Key', prefix: 'xai-', cost: 'credits', note: 'kg_n_xai'),
};
