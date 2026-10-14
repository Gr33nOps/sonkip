cmake_minimum_required(VERSION 3.22)
project(sonkip_runtime C)
include(FetchContent)
FetchContent_Declare(quickjs
    URL https://github.com/quickjs-ng/quickjs/archive/refs/tags/v0.17.0.tar.gz
    URL_HASH SHA256=559bc4c420475e55c7ab4510adbc562f55d7524d75e8e89d79ce4bb02f5687d9)
FetchContent_MakeAvailable(quickjs)
# Android can execute packaged, extracted native libraries, not writable files.
set_target_properties(qjs_exe PROPERTIES OUTPUT_NAME libqjs SUFFIX .so)
install(TARGETS qjs_exe RUNTIME DESTINATION ${ANDROID_ABI})
install(FILES ${quickjs_SOURCE_DIR}/LICENSE DESTINATION licenses RENAME QuickJS.txt)
