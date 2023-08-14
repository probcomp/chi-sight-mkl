from setuptools import setup, find_packages

setup(
    name='xsight',
    version='0.0.1',
    url='https://github.com/probcomp/chi-sight-mkl.git'
    author='Mirko Klukas',
    author_email='mirko.klukas@gmail.com',
    description='Chisight experiments ...',
    packages=find_packages(),    
    install_requires=[],
    package_dir = {'': 'src'}
)
    
