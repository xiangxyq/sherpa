function(download_asio)
  include(FetchContent)

  set(asio_URL  "https://github.com/chriskohlhoff/asio/archive/refs/tags/asio-1-24-0.tar.gz")
  set(asio_HASH "SHA256=cbcaaba0f66722787b1a7c33afe1befb3a012b5af3ad7da7ff0f6b8c9b7a8a5b")

  # If you don't have access to the Internet, please download it to your
  # local drive and modify the following line according to your needs.
  if(EXISTS "/star-fj/fangjun/download/github/asio-asio-1-24-0.tar.gz")
    set(asio_URL  "file:///star-fj/fangjun/download/github/asio-asio-1-24-0.tar.gz")
  elseif(EXISTS "/tmp/asio-asio-1-24-0.tar.gz")
    set(asio_URL  "file:///tmp/asio-asio-1-24-0.tar.gz")
  endif()

  FetchContent_Declare(asio
    URL               ${asio_URL}
    URL_HASH          ${asio_HASH}
  )

  FetchContent_GetProperties(asio)
  if(NOT asio_POPULATED)
    message(STATUS "Downloading asio ${asio_URL}")
    FetchContent_Populate(asio)
  endif()
  message(STATUS "asio is downloaded to ${asio_SOURCE_DIR}")
  # add_subdirectory(${asio_SOURCE_DIR} ${asio_BINARY_DIR} EXCLUDE_FROM_ALL)
  include_directories(${asio_SOURCE_DIR}/asio/include)
endfunction()

download_asio()
