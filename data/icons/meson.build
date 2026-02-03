# Use the application id as the installed icon name so Flatpak export accepts it
icon_name = 'org.gnome.azurevpn'

# Install scalable SVG
scalable_dir = 'hicolor' / 'scalable' / 'apps'
install_data(
  icon_name + '.svg',
  install_dir: get_option('datadir') / 'icons' / scalable_dir
)

# Install PNGs into the hicolor theme hierarchy. Flatpak export expects the
# icon filename to match the application id (e.g. org.gnome.azurevpn.png)
# inside each size directory, so install the files from
# `hicolor/<size>x<size>/apps/org.gnome.azurevpn.png`.
foreach size : ['16', '32', '48', '128', '256']
  src = 'hicolor' / (size + 'x' + size) / 'apps' / (icon_name + '.png')
  install_data(
    src,
    install_dir: get_option('datadir') / 'icons' / 'hicolor' / (size + 'x' + size) / 'apps'
  )
endforeach
