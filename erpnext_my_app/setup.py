from setuptools import setup, find_packages

setup(
    name='erpnext_my_app',
    version='0.0.1',
    description='Simple Hello World API',
    author='Your Name',
    author_email='zeng.lxcy@gmail.com',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=['frappe'],
)
