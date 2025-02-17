function(download_pybind11)
  include(FetchContent)

  set(pybind11_URL  "https://github.com/pybind/pybind11/archive/v2.10.2.tar.gz")
  set(pybind11_HASH "SHA256=93bd1e625e43e03028a3ea7389bba5d3f9f2596abc074b068e70f4ef9b1314ae")

  if(EXISTS "/star-fj/fangjun/download/github/pybind11-2.10.2.tar.gz")
    set(pybind11_URL  "file:///star-fj/fangjun/download/github/pybind11-2.10.2.tar.gz")
  elseif(EXISTS "/tmp/pybind11-2.10.2.tar.gz")
    set(pybind11_URL  "file:///tmp/pybind11-2.10.2.tar.gz")
  endif()

  FetchContent_Declare(pybind11
    URL               ${pybind11_URL}
    URL_HASH          ${pybind11_HASH}
  )

  FetchContent_GetProperties(pybind11)
  if(NOT pybind11_POPULATED)
    message(STATUS "Downloading pybind11")
    FetchContent_Populate(pybind11)
  endif()
  message(STATUS "pybind11 is downloaded to ${pybind11_SOURCE_DIR}")
  add_subdirectory(${pybind11_SOURCE_DIR} ${pybind11_BINARY_DIR} EXCLUDE_FROM_ALL)
endfunction()

download_pybind11()
