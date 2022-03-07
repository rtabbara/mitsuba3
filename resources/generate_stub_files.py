import os
import inspect
import re

import mitsuba as mi

mi.set_variant('llvm_ad_rgb')

# In VS Code you will need to add the following to settings.json:
# "python.analysis.extraPaths": [
#     "${workspaceFolder}/build/python/stub",
# ],

# ------------------------------------------------------------------------------

buffer = ''

def w(s):
    global buffer
    buffer += f'{s}\n'

# ------------------------------------------------------------------------------

def process_type_hint(s):
    sub = s
    type_hints = []
    offset = 0
    while True:
        match = re.search(r'[a-z]+: ', sub)
        if match is None:
            return s
        i = match.start() + len(match.group())
        match_next = re.search(r'[a-z]+: ', sub[i:])
        if match_next is None:
            j = sub.index(')')
        else:
            j = i + match_next.start() - 2
        type_hint = sub[i:j]

        type_hints.append((offset + i, offset + j, sub[i:j]))

        if match_next is None:
            break

        offset = offset + j
        sub = s[offset:]

    offset = 0
    result = ''
    for t in type_hints:
        result += s[offset:t[0]-2]
        offset = t[1]
        # if the type hint is valid, then add it as well
        if not ('::' in t[2]):
            result += f': {t[2]}'
    result += s[offset:]

    # Check is return type hint is not valid
    if '::' in result[result.index(' -> '):]:
        result = result[:result.index(' -> ')]


    # Remove the specific variant hint
    result = result.replace(f'.{mi.variant()}', '')

    return result

# ------------------------------------------------------------------------------

def process_properties(name, p, indent=0):
    indent = ' ' * indent

    if not p is None:
        w(f'{indent}{name} = ...')
        if not p.__doc__ is None:
            doc = p.__doc__.splitlines()
            if len(doc) == 1:
                w(f'{indent}\"{doc[0]}\"')
            elif len(doc) > 1:
                w(f'{indent}\"\"\"')
                for l in doc:
                    w(f'{indent}{l}')
                w(f'{indent}\"\"\"')

# ------------------------------------------------------------------------------

def process_enums(name, e, indent=0):
    indent = ' ' * indent

    if not e is None:
        w(f'{indent}{name} = {int(e)}')

        if not e.__doc__ is None:
            doc = e.__doc__.splitlines()
            w(f'{indent}\"\"\"')
            for l in doc:
                if l.startswith(f'  {name}'):
                    w(f'{indent}{l}')
            w(f'{indent}\"\"\"')

# ------------------------------------------------------------------------------

def process_class(obj):
    methods = []
    properties = []
    enums = []
    for k in dir(obj):
        # Skip private attributes
        if k.startswith('_'):
            continue

        if k.endswith('_'):
            continue

        v = getattr(obj, k)
        if type(v).__name__ == 'instancemethod':
            methods.append((k, v))
        elif type(v).__name__ == 'property':
            properties.append((k, v))
        elif str(v).endswith(k):
            enums.append((k, v))

    w(f'class {obj.__name__}:')
    if obj.__doc__ is not None:
        doc = obj.__doc__.splitlines()
        if len(doc) > 0:
            if doc[0].strip() == '':
                doc = doc[1:]
            if obj.__doc__:
                w(f'    \"\"\"')
                for l in doc:
                    w(f'    {l}')
                w(f'    \"\"\"')
                w(f'')

    process_function('__init__', obj.__init__, indent=4)
    process_function('__call__', obj.__call__, indent=4)

    if len(properties) > 0:
        for k, v in properties:
            process_properties(k, v, indent=4)
        w(f'')

    if len(enums) > 0:
        for k, v in enums:
            process_enums(k, v, indent=4)
        w(f'')

    for k, v in methods:
        process_function(k, v, indent=4)

    w('')

# ------------------------------------------------------------------------------

def process_function(name, obj, indent=0):
    indent = ' ' * indent
    if obj is None or obj.__doc__ is None:
        return

    overloads = []
    for l in obj.__doc__.splitlines():
        if ') -> ' in l:
            l = process_type_hint(l)
            overloads.append((l, []))
        else:
            if len(overloads) > 0:
                overloads[-1][1].append(l)

    for l, doc in overloads:
        has_doc = len(doc) > 1

        # Overload?
        if l[1] == '.':
            w(f"{indent}@overload")
            w(f"{indent}def {l[3:]}:{'' if has_doc else ' ...'}")
        else:
            w(f"{indent}def {l}:{'' if has_doc else ' ...'}")

        if len(doc) > 1: # first line is always empty
            w(f'{indent}    \"\"\"')
            for l in doc[1:]:
                w(f'{indent}    {l}')
            w(f'{indent}    \"\"\"')
            w(f'{indent}    ...')
            w(f'')

# ------------------------------------------------------------------------------

def process_py_function(name, obj, indent=0):
    indent = ' ' * indent
    if obj is None:
        return

    has_doc = obj.__doc__ is not None

    signature = str(inspect.signature(obj))
    signature = signature.replace('\'', '')
    signature = signature.replace('mi.', 'mitsuba.')

    w(f"{indent}def {name}{signature}:{'' if has_doc else ' ...'}")

    if obj.__doc__ is not None:
        doc = obj.__doc__.splitlines()
        if len(doc) > 0: # first line is always empty
            w(f'{indent}    \"\"\"')
            for l in doc:
                w(f'{indent}    {l.strip()}')
            w(f'{indent}    \"\"\"')
            w(f'{indent}    ...')
            w(f'')

# ------------------------------------------------------------------------------

def process_module(m):
    global buffer

    submodules = []
    buffer = ''

    w('from typing import Callable, Iterable, Iterator, Tuple, List, TypeVar, overload, ModuleType')
    w('import numpy')
    w('import mitsuba')
    w('import mitsuba as mi')
    w('')

    for k in dir(m):
        v = getattr(m, k)

        if inspect.isclass(v):
            process_class(v)
            continue
        elif type(v).__name__ in ['method', 'function']:
            process_py_function(k, v)
        elif type(v).__name__ == 'builtin_function_or_method':
            process_function(k, v)
            continue
        elif type(v) in [str, bool, int, float]:
            if k.startswith('_'):
                continue
            process_properties(k, v)
            continue
        elif type(v).__bases__[0].__name__ == 'module' or type(v).__name__ == 'module':
            if k in ['mi', 'mitsuba', 'dr']:
                continue
            w(f'')
            w(f'import .{k} as {k}')
            w('')
            submodules.append((k, v))
        else:
            # print(k, v, type(v))
            pass

    # Adjust DrJIT type hints manually here
    buffer = buffer.replace(f'drjit.{mi.variant()[:4]}.ad.', 'mitsuba.')

    return buffer, submodules

# ------------------------------------------------------------------------------

stub_folder = '../build/python/stub/'

if not os.path.exists(stub_folder):
    os.makedirs(stub_folder)

print(f'Process mitsuba root module')
buffer, submodules = process_module(mi)
with open(f'{stub_folder}mitsuba.pyi', 'w') as f:
    f.write(buffer)

for k, v in submodules:
    print(f'Process submodule: {k}')
    buffer, _ = process_module(v)
    with open(f'{stub_folder}{k}.pyi', 'w') as f:
        f.write(buffer)

print(f'Done -> stub files written to {os.path.abspath(stub_folder)}')