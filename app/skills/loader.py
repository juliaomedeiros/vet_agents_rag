"""
skills/loader.py
────────────────
Carrega o conteúdo de um skill a partir da estrutura de diretórios:

  app/skills/<skill-name>/
      SKILL.md            ← persona principal e regras
      references/*.md     ← documentos de referência (clínica, especialidades…)
      assets/*.md         ← templates de mensagem (boas-vindas, confirmação…)
      scripts/            ← scripts Python auxiliares (não carregados aqui)

O resultado é um dicionário com:
  - "persona"     : conteúdo do SKILL.md (sem o frontmatter YAML)
  - "references"  : dict {nome_arquivo: conteúdo}  (ex: clinic_info, specialties)
  - "assets"      : dict {nome_arquivo: conteúdo}  (ex: welcome_template)
  - "system_prompt": texto consolidado pronto para usar como SystemMessage
"""

import os
import re
from functools import lru_cache
from pathlib import Path

# Localização base dos skills em relação a este arquivo
_SKILLS_DIR = Path(__file__).parent


def _strip_frontmatter(text: str) -> str:
    """Remove o bloco YAML (---..---) do início do markdown."""
    return re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL).strip()


def _load_md_dir(directory: Path) -> dict[str, str]:
    """Lê todos os arquivos .md de um diretório e retorna {stem: conteúdo}."""
    result = {}
    if not directory.exists():
        return result
    for md_file in sorted(directory.glob("*.md")):
        result[md_file.stem] = md_file.read_text(encoding="utf-8").strip()
    return result


@lru_cache(maxsize=16)
def load_skill(skill_name: str) -> dict:
    """
    Carrega e monta um skill pelo nome da pasta.

    Parâmetros
    ----------
    skill_name : str
        Nome da pasta dentro de app/skills/  (ex: "vet-clinic-receptionist")

    Retorna
    -------
    dict com chaves: persona, references, assets, system_prompt
    """
    skill_dir = _SKILLS_DIR / skill_name

    if not skill_dir.exists():
        raise FileNotFoundError(
            f"Skill '{skill_name}' não encontrado em {_SKILLS_DIR}"
        )

    # Lê SKILL.md (persona principal)
    skill_md_path = skill_dir / "SKILL.md"
    persona_raw = skill_md_path.read_text(encoding="utf-8") if skill_md_path.exists() else ""
    persona = _strip_frontmatter(persona_raw)

    # Lê references/ e assets/
    references = _load_md_dir(skill_dir / "references")
    assets = _load_md_dir(skill_dir / "assets")

    # Monta o system_prompt consolidado
    parts = [persona]

    if references:
        parts.append("\n\n## 📚 Documentos de Referência")
        for name, content in references.items():
            parts.append(f"\n### {name.replace('_', ' ').title()}\n{content}")

    if assets:
        parts.append("\n\n## 📝 Templates de Mensagem")
        for name, content in assets.items():
            parts.append(f"\n### {name.replace('_', ' ').title()}\n{content}")

    system_prompt = "\n".join(parts)

    return {
        "persona": persona,
        "references": references,
        "assets": assets,
        "system_prompt": system_prompt,
    }


def get_skill_section(skill_name: str, section: str, key: str) -> str:
    """
    Atalho para obter uma seção específica do skill.

    Exemplos
    --------
    get_skill_section("vet-clinic-receptionist", "references", "clinic_info")
    get_skill_section("vet-clinic-receptionist", "assets", "welcome_template")
    """
    skill = load_skill(skill_name)
    return skill.get(section, {}).get(key, "")
