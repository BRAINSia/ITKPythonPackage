ITKPythonPackage
================

Build infrastructure for ITK Python wheels and ITK external module Python
wheels.

`ITK <https://www.itk.org/>`_ is an open-source, cross-platform system that
provides developers with an extensive suite of software tools for image
analysis.

.. code-block:: bash

   pip install itk

To start using ITK from Python, see the `ITK Python quick start guide
<https://docs.itk.org/en/latest/learn/python_quick_start.html>`_.
For more information on ITK's Python wrapping, see `an introduction in the
Book 1, Chapter 3 of the ITK Software Guide <https://itk.org/ItkSoftwareGuide.pdf>`_.
There are also many `downloadable examples documented in Sphinx
<https://itk.org/ITKExamples/search.html?q=Python>`_.

----

Build Guides
------------

The guides for building ITK Python wheels and ITK module Python wheels are
part of the ITK documentation.

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: Build ITK Python Packages
      :link: https://docs.itk.org/en/latest/contributing/python_packaging.html
      :link-type: url

      Prerequisites, and building core ITK wheels (``itk-core``,
      ``itk-numerics``, ``itk-io``, etc.) from source.

   .. grid-item-card:: Build ITK Module Python Packages
      :link: https://docs.itk.org/en/latest/contributing/python_module_packaging.html
      :link-type: url

      Create, build, and publish Python packages for ITK remote and external
      modules.

----

.. toctree::
   :maxdepth: 1
   :hidden:

   Prerequisites
   Build_ITK_Python_packages
   Build_ITK_Module_Python_packages
   Miscellaneous
