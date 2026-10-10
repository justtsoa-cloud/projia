#include <dlfcn.h>
#include <glob.h>
#include <libgen.h>
#include <limits.h>
#include <unistd.h>

#include <string>

#include "my_application.h"

// Précharge libpython en RTLD_GLOBAL : Dart ouvre libdart_bridge.so en
// RTLD_LOCAL, ce qui masquerait les symboles de libpython aux extensions
// natives du cœur (pydantic-core, pyyaml…) et ferait échouer leur import.
static void preload_libpython() {
  char exe[PATH_MAX];
  ssize_t n = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
  if (n <= 0) return;
  exe[n] = '\0';
  std::string pattern = std::string(dirname(exe)) + "/lib/libpython3.*.so.1.0";
  glob_t g;
  if (glob(pattern.c_str(), 0, nullptr, &g) == 0) {
    for (size_t i = 0; i < g.gl_pathc; i++) {
      dlopen(g.gl_pathv[i], RTLD_NOW | RTLD_GLOBAL);
    }
  }
  globfree(&g);
}

int main(int argc, char** argv) {
  preload_libpython();
  g_autoptr(MyApplication) app = my_application_new();
  return g_application_run(G_APPLICATION(app), argc, argv);
}
