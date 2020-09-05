
%global srcname kojismokydingo
%global srcver 0.9.1


Summary: Koji Smoky Dingo
Name: %{srcname}
Version: %{srcver}
Release: 1%{?dist}
License: GPLv3
Group: Devel
URL: https://github.com/obriencj/koji-smoky-dingo
Source0: %{name}-%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root

BuildArch: noarch


# There's two distinct eras of RPM packaging for python, with
# different macros and different expectations. Generally speaking the
# new features are available in RHEL 8+ and Fedora 22+

%define old_rhel ( 0%{?rhel} && 0%{?rhel} < 8 )
%define old_fedora ( 0%{?fedora} && 0%{?fedora} < 22 )

%if %{old_rhel} || %{old_fedora}
  # old python 2.6 support
  %define with_old_python 1
  %undefine with_python2
  %undefine with_python3
%else
  # newer pythons, with cooler macros
  %undefine with_old_python
  %bcond_with python2
  %bcond_without python3
%endif


# Some older koji fedora packages don't declare their python_provide
# even though the feature was available in the packaging macros. This
# means if we trying to rely on it, we'll produce a Requires for a
# python3.6dist(koji) and no package will ever provide it. Seems to be
# fixed from fedora 28 onwards.
%if ( 0%{?fedora} && 0%{?fedora} > 28 )
  %{?python_enable_dependency_generator}
%endif


%description
Koji Smoky Dingo


%prep
%setup -q


%build

%if %{with old_python}
  %{__python} setup.py build
%endif

%if %{with python2}
  %py2_build_wheel
%endif

%if %{with python3}
  %py3_build_wheel
%endif


%install
rm -rf $RPM_BUILD_ROOT

%if %{with old_python}
  %{__python} setup.py install --skip-build --root %{buildroot}
%endif

%if %{with python2}
  %py2_install_wheel %{srcname}-%{version}-py2-none-any.whl
%endif

%if %{with python3}
  %py3_install_wheel %{srcname}-%{version}-py3-none-any.whl
%endif


%clean
rm -rf $RPM_BUILD_ROOT


%if %{with old_python}
# package support for older python systems (centos 6, fedora
# 19) with only python 2.6 available.

%package -n python2-%{srcname}
Summary:        %{summary}
BuildRequires:  python-setuptools
Requires:	python python-argparse python-setuptools python-six
Requires:       python2-koji
Obsoletes:	python2-%{srcname}-meta

%description -n python2-%{srcname}
Koji Smoky Dingo

%files -n python2-%{srcname}
%defattr(-,root,root,-)
%{python_sitelib}/koji_cli_plugins/
%{python_sitelib}/kojismokydingo/
%{python_sitelib}/kojismokydingo-%{version}-py2.6.egg-info/

%endif


%if %{with python2}

%package -n python2-%{srcname}
Summary:        %{summary}
BuildRequires:  python2-devel python2-pip python2-setuptools python2-wheel
Requires:	python2 python2-setuptools python2-six
Requires:       python2-koji
Obsoletes:	python2-%{srcname}-meta
%{?python_provide:%python_provide python2-%{srcname}}

%description -n python2-%{srcname}
Koji Smoky Dingo

%files -n python2-%{srcname}
%defattr(-,root,root,-)
%{python2_sitelib}/koji_cli_plugins/
%{python2_sitelib}/kojismokydingo/
%{python2_sitelib}/kojismokydingo-%{version}.dist-info/

%endif


%if %{with python3}

%package -n python3-%{srcname}
Summary:        %{summary}
BuildRequires:  python3-devel python3-pip python3-setuptools python3-wheel
Requires:	python3 python3-setuptools python3-six
Requires:       python3-koji
Obsoletes:	python3-%{srcname}-meta
%{?python_provide:%python_provide python3-%{srcname}}

%description -n python3-%{srcname}
Koji Smoky Dingo

%files -n python3-%{srcname}
%defattr(-,root,root,-)
%{python3_sitelib}/koji_cli_plugins/
%{python3_sitelib}/kojismokydingo/
%{python3_sitelib}/kojismokydingo-%{version}.dist-info/

%endif


%changelog

* Fri Sep 04 2020 Christopher O'Brien <obriencj@gmail.com> - 0.9.1-1
- Begin bumping micro for PRs as we work towards version 1.0.0
- All 0.9.z versions are still considered API untable, this just helps
  to differentiate
- Add list-components koji command
- Merged into a single egg/wheel/rpm containing both the lib and the
  meta plugin

* Wed Jan 09 2019 Christopher O'Brien <obriencj@gmail.com> - 0.9.0-1
- Initial build.


# The end.
