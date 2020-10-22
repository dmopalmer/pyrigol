from setuptools import setup

setup(
    name='rigol',
    version='0.0.1',
    packages=['rigol'],
    requires=[
        # 'python>=3.6',    # FIXME How do you write this?
        'pyvisa',
        'numpy'
    ],
    url='',
    license='BSD',
    author='David Palmer',
    author_email='dmopalmer@gmail.com',
    description='Control a Rigol DS1054z (or other) oscilloscope over USB'
)
