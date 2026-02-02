# Publikovanie aplikácie (AzureVPN)

Tento krátky návod popisuje kroky potrebné na zverejnenie novej verzie aplikácie ako Flatpak (lokálne alebo na vzdialenom repozitári ako Flathub).

Požiadavky

- `flatpak-builder`, `flatpak` (client), `meson`, `ninja` (ak používate Meson)
- prístup k repozitáru (GitHub/GitLab) a (voliteľne) konto pre Flathub

1. Príprava verzie

- Aktualizujte verziu v súbore `meson.build` a v metainfo (`org.gnome.azurevpn.metainfo.xml` alebo v manifeste Flatpaku).
- Aktualizujte `CHANGELOG` alebo `NEWS.md` s popisom zmien.

2. Lokálny build (native)

```bash
meson setup _build || meson configure _build
meson compile -C _build
meson test -C _build
```

3. Build ako Flatpak a export do lokálneho repozitára

- Vytvorte priečinok pre build a spustite `flatpak-builder` s BUILD_DIR pred manifestom (DÔLEŽITÉ):

```bash
mkdir -p build-dir
flatpak-builder --force-clean --repo=local-azurevpn build-dir org.gnome.azurevpn.json
```

- Poznámka: syntax je `flatpak-builder [OPTIONS] BUILD_DIR MANIFEST` — ak vynecháte `BUILD_DIR`, build zlyhá.

4. Aktualizácia metadát repozitára (AppStream / summary)

```bash
flatpak build-update-repo local-azurevpn
```

- Po spustení sa vytvorí/aktualizuje vetva `appstream` a `summary`, ktoré používa GNOME Software.

5. Pridanie lokálneho repozitára ako remote a inštalácia/aktualizácia

- Pridať remote (používateľská inštalácia):

```bash
flatpak --user remote-add --no-gpg-verify azurevpn-local file:///home/predrag/Projekty/azureVpn/local-azurevpn
```

- Inštalovať alebo preinštalovať aplikáciu z lokálneho remote:

```bash
flatpak --user install --reinstall azurevpn-local org.gnome.azurevpn -y
# alebo aktualizovať existujúcu inštaláciu
flatpak --user update org.gnome.azurevpn --from=azurevpn-local
```

6. Ak GNOME Software stále zobrazuje starú verziu

- Skontrolujte, či v metainfo (`org.gnome.azurevpn.metainfo.xml`) je správne nastavené `<release>`/`<version>`.
- Uistite sa, že ste spustili `flatpak build-update-repo` (AppStream sa generuje/aktualizuje).
- Reštartujte GNOME Software:

```bash
killall gnome-software || true
gnome-software & disown
```

7. Publikovanie na Flathub / verejné repo

- Flathub používa manifest PR workflow. Pre publikovanie na Flathub postupujte podľa oficiálnej dokumentácie: spravidla vytvoríte PR v repozitári `flathub` alebo použijete návod pre `flathub` packaging (manifest, CI checks).
- Ak potrebujete uploadovať artefakty inde, vytvorte GitHub Release a nahrajte `dist/` súbory alebo `.flatpakref` (ak ho generujete externým nástrojom).

8. Automatizácia (odporúčané)

- Nastavte CI (GitHub Actions / GitLab CI) ktoré:
  - upraví verziu pri tagu, spustí unit testy
  - spustí `flatpak-builder` a buď exportuje do repozitára, alebo spraví `.flatpakref` a nahodí artifacty do Release

Užitočné tipy

- Vždy overte lokálny build a testy pred publikovaním.
- Ak používate GPG podpisy pre repozitár, použite `flatpak build-update-repo --gpg-sign=KEY-ID`.
- Pre vyriešenie problémov so starou verziou v GNOME Software skontrolujte AppStream XML (metainfo) — GNOME Software číta verziu z AppStream/metainfo.

Ak chceš, môžem:

- spustiť teraz `flatpak-builder` + `flatpak build-update-repo` a nainštalovať novú verziu lokálne,
- alebo pripraviť GitHub Actions workflow pre automatizáciu build+publish.

# azurevpn

A description of this project.
