"""Short-lived static analysis worker. Never import or run the user's project."""
import json
import sys


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    except (ImportError, ValueError, OSError):
        pass
    import jedi
    data = json.load(sys.stdin)
    jedi.settings.auto_import_modules = []
    jedi.settings.cache_directory = data['cache']
    project = jedi.Project(data['root'], sys_path=[data['root'], *sys.path],
                           smart_sys_path=False, load_unsafe_extensions=False)
    script = jedi.Script(data['content'], path=data['path'], project=project)
    definitions = script.goto(data['line'], data['column'], follow_imports=True)
    result = [dict(path=str(d.module_path), line=d.line, column=d.column, name=d.name)
              for d in definitions[:20] if d.module_path and d.line is not None]
    print(json.dumps(result))


if __name__ == '__main__':
    main()
