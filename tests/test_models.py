"""Tests for the models module."""

import yaml

from lola.models import (
    Skill,
    Command,
    Module,
    Installation,
    InstallationRegistry,
)
from lola.frontmatter import validate_skill


class TestSkill:
    """Tests for Skill dataclass."""

    def test_from_path_with_skill_file(self, tmp_path):
        """Load skill from directory with SKILL.md."""
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: myskill
description: A test skill
---

Content.
""")
        skill = Skill.from_path(skill_dir)
        assert skill.name == "myskill"
        assert skill.path == skill_dir
        assert skill.description == "A test skill"

    def test_from_path_without_skill_file(self, tmp_path):
        """Load skill from directory without SKILL.md."""
        skill_dir = tmp_path / "myskill"
        skill_dir.mkdir()

        skill = Skill.from_path(skill_dir)
        assert skill.name == "myskill"
        assert skill.description is None


class TestCommand:
    """Tests for Command dataclass."""

    def test_from_path_with_frontmatter(self, tmp_path):
        """Load command from file with frontmatter."""
        cmd_file = tmp_path / "test.md"
        cmd_file.write_text("""---
description: Test command
argument-hint: "<file>"
---

Do something.
""")
        cmd = Command.from_path(cmd_file)
        assert cmd.name == "test"
        assert cmd.description == "Test command"
        assert cmd.argument_hint == "<file>"

    def test_from_path_without_file(self, tmp_path):
        """Load command when file doesn't exist."""
        cmd_file = tmp_path / "nonexistent.md"

        cmd = Command.from_path(cmd_file)
        assert cmd.name == "nonexistent"
        assert cmd.description is None
        assert cmd.argument_hint is None


class TestModule:
    """Tests for Module dataclass."""

    def test_from_path_valid_module_with_skills(self, tmp_path):
        """Load valid module with auto-discovered skills."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create skills directory with skill subdirectories
        skills_dir = module_dir / "skills"
        skills_dir.mkdir()
        for skill in ["skill1", "skill2"]:
            skill_dir = skills_dir / skill
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(f"""---
description: {skill} description
---

Content.
""")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.name == "mymodule"
        assert module.skills == ["skill1", "skill2"]

    def test_from_path_valid_module_with_commands(self, tmp_path):
        """Load valid module with auto-discovered commands."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create commands directory
        commands_dir = module_dir / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("Command content")
        (commands_dir / "cmd2.md").write_text("Command content")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.commands == ["cmd1", "cmd2"]

    def test_from_path_empty_directory(self, tmp_path):
        """Return None when directory has no skills or commands."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        module = Module.from_path(module_dir)
        assert module is None

    def test_from_path_skips_hidden_directories(self, tmp_path):
        """Skip hidden directories when discovering skills."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create skills directory
        skills_dir = module_dir / "skills"
        skills_dir.mkdir()

        # Create hidden directory with SKILL.md (should be skipped)
        hidden_dir = skills_dir / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "SKILL.md").write_text("---\ndescription: test\n---\n")

        # Create valid skill
        skill_dir = skills_dir / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\n")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.skills == ["myskill"]
        assert ".hidden" not in module.skills

    def test_from_path_skips_commands_folder_as_skill(self, tmp_path):
        """Don't treat commands folder as a skill even if it has SKILL.md."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create commands directory with a command file
        commands_dir = module_dir / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("Command content")

        # Create skills directory with a valid skill
        skills_dir = module_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\n")

        module = Module.from_path(module_dir)
        assert module is not None
        assert "commands" not in module.skills
        assert module.skills == ["myskill"]
        assert module.commands == ["cmd1"]

    def test_get_skill_paths(self, tmp_path):
        """Get full paths to skills."""
        module = Module(
            name="test",
            path=tmp_path,
            content_path=tmp_path,
            skills=["skill1", "skill2"],
        )
        paths = module.get_skill_paths()
        assert len(paths) == 2
        assert paths[0] == tmp_path / "skills" / "skill1"
        assert paths[1] == tmp_path / "skills" / "skill2"

    def test_get_command_paths(self, tmp_path):
        """Get full paths to commands."""
        module = Module(
            name="test", path=tmp_path, content_path=tmp_path, commands=["cmd1", "cmd2"]
        )
        paths = module.get_command_paths()
        assert len(paths) == 2
        assert paths[0] == tmp_path / "commands" / "cmd1.md"
        assert paths[1] == tmp_path / "commands" / "cmd2.md"

    def test_from_path_with_module_subdirectory(self, tmp_path):
        """Load module with content in module/ subdirectory."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create module/ subdirectory with content
        content_dir = module_dir / "module"
        content_dir.mkdir()

        # Create skills directory with skill
        skills_dir = content_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "skill1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
description: A skill in module/ subdir
---

Content.
""")

        # Create command
        commands_dir = content_dir / "commands"
        commands_dir.mkdir()
        (commands_dir / "cmd1.md").write_text("Command content")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.name == "mymodule"
        assert module.path == module_dir
        assert module.content_path == content_dir
        assert module.uses_module_subdir is True
        assert module.skills == ["skill1"]
        assert module.commands == ["cmd1"]

    def test_from_path_prefers_module_subdirectory(self, tmp_path):
        """Prefer module/ subdirectory over root-level content."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create root-level skill (should be ignored)
        root_skills = module_dir / "skills"
        root_skills.mkdir()
        root_skill = root_skills / "root-skill"
        root_skill.mkdir()
        (root_skill / "SKILL.md").write_text("---\ndescription: root skill\n---\n")

        # Create module/ subdirectory with different skill
        content_dir = module_dir / "module"
        content_dir.mkdir()
        module_skills = content_dir / "skills"
        module_skills.mkdir()
        module_skill = module_skills / "module-skill"
        module_skill.mkdir()
        (module_skill / "SKILL.md").write_text("---\ndescription: module skill\n---\n")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.uses_module_subdir is True
        assert module.skills == ["module-skill"]
        assert "root-skill" not in module.skills

    def test_from_path_with_custom_content_dirname(self, tmp_path):
        """Load module with custom content directory using content_dirname parameter."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create lola-module/ subdirectory with content
        content_dir = module_dir / "lola-module"
        content_dir.mkdir()

        # Create skills directory with skill
        skills_dir = content_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "skill1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
description: A skill in custom subdir
---

Content.
""")

        # Must explicitly specify content_dirname now
        module = Module.from_path(module_dir, content_dirname="lola-module")
        assert module is not None
        assert module.name == "mymodule"
        assert module.path == module_dir
        assert module.content_path == content_dir
        assert module.uses_module_subdir is True
        assert module.skills == ["skill1"]

    def test_from_path_with_root_content_dirname(self, tmp_path):
        """Load module from root directory using content_dirname='/'."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create skills directory directly in root (no module/ subdir)
        skills_dir = module_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "root-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: root skill\n---\n")

        # Explicitly request root directory
        module = Module.from_path(module_dir, content_dirname="/")
        assert module is not None
        assert module.uses_module_subdir is False
        assert module.content_path == module_dir
        assert module.skills == ["root-skill"]

    def test_from_path_falls_back_to_root(self, tmp_path):
        """Fall back to root-level content when module/ doesn't exist."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create root-level skill only (no module/ subdir)
        skills_dir = module_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "skill1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\n")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.uses_module_subdir is False
        assert module.content_path == module_dir
        assert module.skills == ["skill1"]

    def test_get_paths_with_module_subdirectory(self, tmp_path):
        """Get paths respects content_path for module/ subdirectory."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()
        content_dir = module_dir / "module"
        content_dir.mkdir()

        module = Module(
            name="test",
            path=module_dir,
            content_path=content_dir,
            skills=["skill1"],
            commands=["cmd1"],
            agents=["agent1"],
            uses_module_subdir=True,
        )

        skill_paths = module.get_skill_paths()
        assert skill_paths[0] == content_dir / "skills" / "skill1"

        cmd_paths = module.get_command_paths()
        assert cmd_paths[0] == content_dir / "commands" / "cmd1.md"

        agent_paths = module.get_agent_paths()
        assert agent_paths[0] == content_dir / "agents" / "agent1.md"

    def test_validate_valid_module(self, tmp_path):
        """Validate a correctly structured module."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create skills directory with skill
        skills_dir = module_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "skill1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
description: A skill
---

Content.
""")

        # Create command with valid frontmatter
        cmd_dir = module_dir / "commands"
        cmd_dir.mkdir()
        (cmd_dir / "cmd1.md").write_text("""---
description: A command
---

Content.
""")

        module = Module.from_path(module_dir)
        assert module is not None
        is_valid, errors = module.validate()
        assert is_valid is True
        assert errors == []

    def test_validate_skill_missing_description(self, tmp_path):
        """Validate module with skill missing description in frontmatter."""
        module_dir = tmp_path / "mymodule"
        module_dir.mkdir()

        # Create skills directory with skill missing description
        skills_dir = module_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "skill1"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: skill1
---

Content.
""")

        module = Module.from_path(module_dir)
        assert module is not None
        is_valid, errors = module.validate()
        assert is_valid is False
        assert any("description" in e.lower() for e in errors)


class TestModuleMetadata:
    """Tests for lola.yaml module metadata parsing and validation."""

    def test_from_path_with_full_metadata(self, sample_module_with_metadata):
        """Module with full lola.yaml populates all metadata fields."""
        module = Module.from_path(sample_module_with_metadata)
        assert module is not None
        assert module.version == "1.2.3"
        assert module.description == "A test module with metadata"
        assert module.author == "Test Author <test@example.com>"
        assert module.license == "MIT"
        assert sorted(module.tags) == ["example", "testing"]
        assert module.homepage == "https://example.com/meta-module"
        assert module.repository == "https://github.com/test/meta-module.git"
        assert module.lola_version == ">=0.8.0"

    def test_from_path_with_partial_metadata(self, tmp_path):
        """Module with only version in lola.yaml; other fields remain None."""
        module_dir = tmp_path / "partial-module"
        content_dir = module_dir / "module"
        skill_dir = content_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )
        (content_dir / "lola.yaml").write_text("version: 2.0.0\n")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.version == "2.0.0"
        assert module.description is None
        assert module.author is None
        assert module.tags == []

    def test_from_path_without_lola_yaml(self, sample_module):
        """Module without lola.yaml has all metadata fields empty/None."""
        module = Module.from_path(sample_module)
        assert module is not None
        assert module.version is None
        assert module.description is None
        assert module.author is None
        assert module.license is None
        assert module.tags == []
        assert module.homepage is None
        assert module.repository is None
        assert module.lola_version is None

    def test_version_float_cast_to_string(self, tmp_path):
        """YAML bare 1.0 (parsed as float) is cast to string."""
        module_dir = tmp_path / "float-version"
        content_dir = module_dir
        skill_dir = content_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )
        (content_dir / "lola.yaml").write_text("version: 1.0\n")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.version == "1.0"
        assert isinstance(module.version, str)

    def test_malformed_lola_yaml_graceful(self, tmp_path):
        """Malformed lola.yaml doesn't crash; metadata fields stay empty."""
        module_dir = tmp_path / "bad-yaml"
        skill_dir = module_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )
        (module_dir / "lola.yaml").write_text("{{invalid yaml: [")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.version is None
        assert module.tags == []

    def test_validate_valid_version(self, tmp_path):
        """Valid PEP 440 versions pass validation."""
        module_dir = tmp_path / "valid-ver"
        skill_dir = module_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )
        (module_dir / "lola.yaml").write_text("version: 1.2.3\n")

        module = Module.from_path(module_dir)
        assert module is not None
        is_valid, errors = module.validate()
        assert is_valid is True
        assert not any("version" in e.lower() for e in errors)

    def test_validate_invalid_version(self, tmp_path):
        """Invalid version string produces validation error."""
        module_dir = tmp_path / "bad-ver"
        skill_dir = module_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )
        (module_dir / "lola.yaml").write_text("version: not-a-version\n")

        module = Module.from_path(module_dir)
        assert module is not None
        is_valid, errors = module.validate()
        assert is_valid is False
        assert any("version" in e.lower() for e in errors)

    def test_validate_invalid_lola_version(self, tmp_path):
        """Invalid lola-version specifier produces validation error."""
        module_dir = tmp_path / "bad-lola-ver"
        skill_dir = module_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )
        (module_dir / "lola.yaml").write_text(
            "version: 1.0.0\nlola-version: \"not a specifier!!!\"\n"
        )

        module = Module.from_path(module_dir)
        assert module is not None
        is_valid, errors = module.validate()
        assert is_valid is False
        assert any("lola-version" in e for e in errors)

    def test_validate_valid_lola_version_specifiers(self, tmp_path):
        """Various valid specifier formats pass validation."""
        for spec in [">=0.8.0", ">=0.8.0,<2.0", ">=1.0", "==1.2.3", "~=1.2"]:
            module_dir = tmp_path / f"spec-{spec.replace(',', '_')}"
            skill_dir = module_dir / "skills" / "s1"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\ndescription: A skill\n---\nContent.\n"
            )
            (module_dir / "lola.yaml").write_text(
                f'version: 1.0.0\nlola-version: "{spec}"\n'
            )

            module = Module.from_path(module_dir)
            assert module is not None
            is_valid, errors = module.validate()
            assert is_valid is True, f"Specifier {spec!r} should be valid but got: {errors}"

    def test_validate_for_publish_complete(self, sample_module_with_metadata):
        """Module with all required publish fields passes."""
        module = Module.from_path(sample_module_with_metadata)
        assert module is not None
        is_valid, errors = module.validate_for_publish()
        assert is_valid is True
        assert errors == []

    def test_validate_for_publish_missing_fields(self, tmp_path):
        """Module missing publish-required fields fails."""
        module_dir = tmp_path / "no-publish"
        skill_dir = module_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )

        module = Module.from_path(module_dir)
        assert module is not None
        is_valid, errors = module.validate_for_publish()
        assert is_valid is False
        assert any("version" in e for e in errors)
        assert any("description" in e for e in errors)
        assert any("author" in e for e in errors)
        assert any("repository" in e for e in errors)

    def test_tags_non_list_ignored(self, tmp_path):
        """tags that isn't a list is ignored gracefully."""
        module_dir = tmp_path / "bad-tags"
        skill_dir = module_dir / "skills" / "s1"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\nContent.\n"
        )
        (module_dir / "lola.yaml").write_text("version: 1.0.0\ntags: not-a-list\n")

        module = Module.from_path(module_dir)
        assert module is not None
        assert module.tags == []


class TestValidateSkill:
    """Tests for validate_skill()."""

    def test_valid_frontmatter(self, tmp_path):
        """Validate valid SKILL.md."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: myskill
description: My skill description
---

Content.
""")
        errors = validate_skill(skill_file)
        assert errors == []

    def test_missing_frontmatter(self, tmp_path):
        """Validate file without frontmatter."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Just content")

        errors = validate_skill(skill_file)
        assert len(errors) == 1
        assert "frontmatter" in errors[0].lower()

    def test_missing_description(self, tmp_path):
        """Validate file without description field."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: myskill
---

Content.
""")
        errors = validate_skill(skill_file)
        assert len(errors) == 1
        assert "description" in errors[0].lower()


class TestInstallation:
    """Tests for Installation dataclass."""

    def test_to_dict(self):
        """Convert installation to dictionary."""
        inst = Installation(
            module_name="mymodule",
            assistant="claude-code",
            scope="user",
            skills=["skill1"],
            commands=["cmd1"],
        )
        d = inst.to_dict()
        assert d["module"] == "mymodule"
        assert d["assistant"] == "claude-code"
        assert d["scope"] == "user"
        assert d["skills"] == ["skill1"]
        assert d["commands"] == ["cmd1"]
        assert "project_path" not in d

    def test_to_dict_with_project_path(self):
        """Convert installation with project path to dictionary."""
        inst = Installation(
            module_name="mymodule",
            assistant="cursor",
            scope="project",
            project_path="/path/to/project",
            skills=["skill1"],
        )
        d = inst.to_dict()
        assert d["project_path"] == "/path/to/project"

    def test_from_dict(self):
        """Create installation from dictionary."""
        d = {
            "module": "mymodule",
            "assistant": "claude-code",
            "scope": "user",
            "skills": ["skill1", "skill2"],
            "commands": ["cmd1"],
        }
        inst = Installation.from_dict(d)
        assert inst.module_name == "mymodule"
        assert inst.assistant == "claude-code"
        assert inst.scope == "user"
        assert inst.skills == ["skill1", "skill2"]
        assert inst.commands == ["cmd1"]


class TestInstallationRegistry:
    """Tests for InstallationRegistry."""

    def test_empty_registry(self, tmp_path):
        """Create registry when file doesn't exist."""
        registry_path = tmp_path / "installed.yml"
        registry = InstallationRegistry(registry_path)
        assert registry.all() == []

    def test_add_installation(self, tmp_path):
        """Add installation to registry."""
        registry_path = tmp_path / "installed.yml"
        registry = InstallationRegistry(registry_path)

        inst = Installation(
            module_name="mymodule",
            assistant="claude-code",
            scope="user",
            skills=["skill1"],
        )
        registry.add(inst)

        assert len(registry.all()) == 1
        assert registry_path.exists()

    def test_add_replaces_existing(self, tmp_path):
        """Adding installation with same key replaces existing."""
        registry_path = tmp_path / "installed.yml"
        registry = InstallationRegistry(registry_path)

        inst1 = Installation(
            module_name="mymodule",
            assistant="claude-code",
            scope="user",
            skills=["skill1"],
        )
        registry.add(inst1)

        inst2 = Installation(
            module_name="mymodule",
            assistant="claude-code",
            scope="user",
            skills=["skill1", "skill2"],
        )
        registry.add(inst2)

        all_inst = registry.all()
        assert len(all_inst) == 1
        assert all_inst[0].skills == ["skill1", "skill2"]

    def test_find_by_module(self, tmp_path):
        """Find installations by module name."""
        registry_path = tmp_path / "installed.yml"
        registry = InstallationRegistry(registry_path)

        registry.add(Installation("mod1", "claude-code", "user"))
        registry.add(Installation("mod1", "cursor", "project", "/path"))
        registry.add(Installation("mod2", "claude-code", "user"))

        found = registry.find("mod1")
        assert len(found) == 2

    def test_remove_all_by_module(self, tmp_path):
        """Remove all installations of a module."""
        registry_path = tmp_path / "installed.yml"
        registry = InstallationRegistry(registry_path)

        registry.add(Installation("mod1", "claude-code", "user"))
        registry.add(Installation("mod1", "cursor", "user"))
        registry.add(Installation("mod2", "claude-code", "user"))

        removed = registry.remove("mod1")
        assert len(removed) == 2
        assert len(registry.all()) == 1

    def test_remove_specific_installation(self, tmp_path):
        """Remove specific installation by all criteria."""
        registry_path = tmp_path / "installed.yml"
        registry = InstallationRegistry(registry_path)

        registry.add(Installation("mod1", "claude-code", "user"))
        registry.add(Installation("mod1", "cursor", "user"))

        removed = registry.remove("mod1", assistant="claude-code", scope="user")
        assert len(removed) == 1
        assert len(registry.all()) == 1
        assert registry.all()[0].assistant == "cursor"

    def test_load_existing_registry(self, tmp_path):
        """Load registry from existing file."""
        registry_path = tmp_path / "installed.yml"
        data = {
            "version": "1.0",
            "installations": [
                {
                    "module": "mod1",
                    "assistant": "claude-code",
                    "scope": "user",
                    "skills": ["s1"],
                },
                {
                    "module": "mod2",
                    "assistant": "cursor",
                    "scope": "project",
                    "project_path": "/p",
                    "skills": [],
                },
            ],
        }
        registry_path.write_text(yaml.dump(data))

        registry = InstallationRegistry(registry_path)
        assert len(registry.all()) == 2

    def test_atomic_save_no_temp_files(self, tmp_path):
        """Verify atomic save doesn't leave temporary files behind."""
        registry_path = tmp_path / "installed.yml"
        registry = InstallationRegistry(registry_path)

        # Add multiple installations to trigger saves
        registry.add(Installation("mod1", "claude-code", "user"))
        registry.add(Installation("mod2", "cursor", "user"))

        # Verify registry file exists
        assert registry_path.exists()

        # Verify no temporary files are left in the directory
        temp_files = list(tmp_path.glob(".installed.yml.*.tmp"))
        assert len(temp_files) == 0, f"Found temporary files: {temp_files}"

        # Verify the file is valid YAML and contains our data
        with open(registry_path) as f:
            data = yaml.safe_load(f)
        assert data["version"] == "1.0"
        assert len(data["installations"]) == 2

    def test_atomic_save_creates_parent_dirs(self, tmp_path):
        """Verify atomic save creates parent directories."""
        registry_path = tmp_path / "subdir" / "nested" / "installed.yml"
        registry = InstallationRegistry(registry_path)

        registry.add(Installation("mod1", "claude-code", "user"))

        # Verify parent directories were created
        assert registry_path.parent.exists()
        assert registry_path.exists()

        # Verify no temp files in any parent directory
        for parent in registry_path.parents:
            if parent == tmp_path:
                break
            temp_files = list(parent.glob(".installed.yml.*.tmp"))
            assert len(temp_files) == 0
