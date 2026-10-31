"""Rutas: los assets viven en el paquete y los datos en la raiz del repo.

Si alguien mueve carpetas, este test avisa antes de que la app arranque sin
fuentes, sin icono o escribiendo el config dentro de src/.
"""

from pathlib import Path

from tradedesk import paths


def test_los_assets_del_paquete_existen():
    assert paths.ASSETS.is_dir()
    assert (paths.ASSETS / "icon.ico").is_file()
    assert (paths.ASSETS / "icon.png").is_file()


def test_las_fuentes_geist_estan_registradas_en_el_repo():
    fuentes = list((paths.ASSETS / "fonts").glob("*.ttf"))
    assert len(fuentes) >= 5, f"faltan fuentes: {fuentes}"


def test_los_datos_del_usuario_quedan_fuera_del_paquete():
    raiz_del_repo = Path(paths.PACKAGE_DIR).parents[1]
    assert raiz_del_repo == paths.DATA_DIR
    assert "src" not in paths.DATA_DIR.parts
    assert paths.DATA_DIR != paths.PACKAGE_DIR
